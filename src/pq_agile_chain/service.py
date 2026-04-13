from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from threading import Lock
from typing import Any

from .chain import PQAgileChain
from .crypto_backends import DEFAULT_ALGO_ID, supported_algorithms
from .wallets import create_wallet, load_wallet, save_wallet

_WALLET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class WorkspaceError(RuntimeError):
    """Raised when the local workspace is missing data or invalid."""


class ChainWorkspace:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        default_root = Path.cwd() / "data"
        self.root_dir = Path(
            root_dir or os.environ.get("PQ_AGILE_CHAIN_DATA_DIR", default_root)
        )
        self.chain_path = self.root_dir / "chain.json"
        self.wallets_dir = self.root_dir / "wallets"
        self._lock = Lock()

    def snapshot(self) -> dict[str, Any]:
        chain = self._load_chain_if_present()
        accounts = chain.account_snapshots(include_mempool=True) if chain else []
        active_by_account = {account["account_id"]: account for account in accounts}

        wallets = []
        wallet_paths = (
            sorted(self.wallets_dir.glob("*.wallet.json"))
            if self.wallets_dir.exists()
            else []
        )
        for path in wallet_paths:
            wallet_id = path.name.removesuffix(".wallet.json")
            wallet = load_wallet(path)
            active_account = active_by_account.get(wallet.account_id)
            is_active = bool(
                active_account
                and active_account["algo_id"] == wallet.algo_id
                and active_account["public_key"] == wallet.public_key
            )
            wallets.append(
                {
                    "wallet_id": wallet_id,
                    "label": wallet.label,
                    "account_id": wallet.account_id,
                    "algo_id": wallet.algo_id,
                    "security_floor": wallet.security_floor,
                    "active_on_chain": is_active,
                }
            )

        blocks = [block.to_dict() for block in chain.blocks] if chain else []
        mempool = list(chain.mempool) if chain else []
        return {
            "site": {
                "host_hint": "qc.jrti.org",
                "brand": "JRTI",
                "brand_ko": "법률·언어·인공지능 통섭연구소",
                "app_name": "PQ-Agile Chain",
                "tagline": "Post-quantum chain demo with on-chain key rotation",
            },
            "supported_algorithms": supported_algorithms(),
            "workspace": {
                "root_dir": str(self.root_dir),
                "chain_path": str(self.chain_path),
                "has_chain": chain is not None,
            },
            "chain": chain.to_dict() if chain else None,
            "blocks": blocks,
            "mempool": mempool,
            "accounts": accounts,
            "wallets": wallets,
        }

    def reset_demo(self, *, difficulty: int = 2) -> dict[str, Any]:
        with self._lock:
            if self.root_dir.exists():
                shutil.rmtree(self.root_dir)
            self.wallets_dir.mkdir(parents=True, exist_ok=True)

            alice = create_wallet(
                algo_id=DEFAULT_ALGO_ID,
                label="alice",
                security_floor=3,
            )
            bob = create_wallet(
                algo_id=DEFAULT_ALGO_ID,
                label="bob",
                security_floor=3,
            )
            save_wallet(alice, self._wallet_path("alice"))
            save_wallet(bob, self._wallet_path("bob"))

            chain = PQAgileChain.bootstrap(
                difficulty=difficulty,
                wallet_allocations=[(alice, 120), (bob, 25)],
            )
            chain.save(self.chain_path)
            return self.snapshot()

    def transfer(
        self,
        *,
        sender_wallet_id: str,
        recipient_wallet_id: str | None,
        recipient_account_id: str | None,
        amount: int,
    ) -> dict[str, Any]:
        with self._lock:
            chain = self._load_chain()
            sender_wallet = self._load_wallet(sender_wallet_id)
            if recipient_wallet_id:
                recipient_account_id = self._load_wallet(recipient_wallet_id).account_id
            if recipient_account_id is None:
                raise WorkspaceError("recipient_wallet_id or recipient_account_id is required")

            tx = chain.queue_transfer(
                sender_wallet=sender_wallet,
                recipient_account_id=recipient_account_id,
                amount=amount,
            )
            chain.save(self.chain_path)
            return {"transaction": tx.to_dict(), "snapshot": self.snapshot()}

    def rotate(
        self,
        *,
        current_wallet_id: str,
        new_algo_id: str,
        new_wallet_id: str | None = None,
        new_label: str | None = None,
        new_security_floor: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            chain = self._load_chain()
            current_wallet = self._load_wallet(current_wallet_id)
            wallet_id = new_wallet_id or self._next_wallet_id(
                f"{current_wallet_id}-{new_algo_id.replace('-', '_')}"
            )
            floor = (
                current_wallet.security_floor
                if new_security_floor is None
                else new_security_floor
            )
            new_wallet = create_wallet(
                algo_id=new_algo_id,
                label=new_label or f"{current_wallet.label}-{new_algo_id}",
                security_floor=floor,
                account_id=current_wallet.account_id,
            )
            tx = chain.queue_rotation(current_wallet=current_wallet, new_wallet=new_wallet)
            save_wallet(new_wallet, self._wallet_path(wallet_id))
            chain.save(self.chain_path)
            return {
                "wallet_id": wallet_id,
                "transaction": tx.to_dict(),
                "snapshot": self.snapshot(),
            }

    def mine(self) -> dict[str, Any]:
        with self._lock:
            chain = self._load_chain()
            block = chain.mine_pending()
            chain.save(self.chain_path)
            return {"block": block.to_dict(), "snapshot": self.snapshot()}

    def _load_chain(self) -> PQAgileChain:
        if not self.chain_path.exists():
            raise WorkspaceError("chain.json is missing; initialize the demo first")
        return PQAgileChain.load(self.chain_path)

    def _load_chain_if_present(self) -> PQAgileChain | None:
        if not self.chain_path.exists():
            return None
        return PQAgileChain.load(self.chain_path)

    def _load_wallet(self, wallet_id: str):
        return load_wallet(self._wallet_path(wallet_id))

    def _wallet_path(self, wallet_id: str) -> Path:
        if not _WALLET_ID_RE.fullmatch(wallet_id):
            raise WorkspaceError(
                "wallet_id must match ^[a-z0-9][a-z0-9_-]{0,63}$"
            )
        return self.wallets_dir / f"{wallet_id}.wallet.json"

    def _next_wallet_id(self, base_wallet_id: str) -> str:
        stem = self._sanitize_wallet_id(base_wallet_id)
        candidate = stem
        index = 2
        while self._wallet_path(candidate).exists():
            suffix = f"-{index}"
            candidate = f"{stem[: 64 - len(suffix)]}{suffix}"
            index += 1
        return candidate

    @staticmethod
    def _sanitize_wallet_id(raw_value: str) -> str:
        lowered = raw_value.lower().replace(".", "-")
        sanitized = re.sub(r"[^a-z0-9_-]+", "-", lowered).strip("-")
        if not sanitized:
            return "wallet"
        return sanitized[:64]
