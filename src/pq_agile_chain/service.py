from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from threading import Lock
from typing import Any

from .chain import PQAgileChain
from .crypto_backends import DEFAULT_ALGO_ID, supported_algorithms
from .wallets import (
    create_wallet,
    load_wallet,
    resolve_wallet_password,
    save_wallet,
)

_WALLET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DEFAULT_WALLET_PASSWORD_ENV = "PQ_AGILE_CHAIN_WALLET_PASSWORD"


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
        self.wallet_password = resolve_wallet_password(
            default_env=_DEFAULT_WALLET_PASSWORD_ENV
        )
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
                    "secret_storage": wallet.secret_key_format,
                    "encrypted": wallet.is_encrypted,
                }
            )

        mempool = list(chain.mempool) if chain else []
        latest_block = self._block_summary(chain.blocks[-1]) if chain and chain.blocks else None
        return {
            "site": {
                "host_hint": "jrti.org/qc",
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
            "chain": self._chain_summary(chain),
            "latest_block": latest_block,
            "mempool": mempool,
            "accounts": accounts,
            "wallets": wallets,
        }

    def list_blocks(self, *, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        chain = self._load_chain_if_present()
        if chain is None:
            return {
                "items": [],
                "offset": offset,
                "limit": limit,
                "total": 0,
                "order": "desc",
            }

        ordered_blocks = list(reversed(chain.blocks))
        items = [
            self._block_summary(block)
            for block in ordered_blocks[offset : offset + limit]
        ]
        return {
            "items": items,
            "offset": offset,
            "limit": limit,
            "total": len(ordered_blocks),
            "order": "desc",
        }

    def list_transactions(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        include_mempool: bool = True,
    ) -> dict[str, Any]:
        chain = self._load_chain_if_present()
        if chain is None:
            return {
                "items": [],
                "offset": offset,
                "limit": limit,
                "total": 0,
                "order": "desc",
            }

        items: list[dict[str, Any]] = []
        if include_mempool:
            for tx in reversed(chain.mempool):
                items.append(
                    self._transaction_summary(
                        tx,
                        block_index=None,
                        position=None,
                        status="pending",
                    )
                )

        for block in reversed(chain.blocks):
            for position, tx in reversed(list(enumerate(block.transactions))):
                items.append(
                    self._transaction_summary(
                        tx,
                        block_index=block.index,
                        position=position,
                        status="confirmed",
                    )
                )

        return {
            "items": items[offset : offset + limit],
            "offset": offset,
            "limit": limit,
            "total": len(items),
            "order": "desc",
        }

    def reset_demo(self, *, difficulty: int = 2) -> dict[str, Any]:
        with self._lock:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            for path in self.root_dir.iterdir():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            self.wallets_dir.mkdir(parents=True, exist_ok=True)

            alice = create_wallet(
                algo_id=DEFAULT_ALGO_ID,
                label="alice",
                security_floor=3,
                password=self.wallet_password,
            )
            bob = create_wallet(
                algo_id=DEFAULT_ALGO_ID,
                label="bob",
                security_floor=3,
                password=self.wallet_password,
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
            sender_wallet = self._load_wallet(sender_wallet_id, require_secret=True)
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
            current_wallet = self._load_wallet(current_wallet_id, require_secret=True)
            wallet_id = new_wallet_id or self._next_wallet_id(
                f"{current_wallet_id}-{new_algo_id.replace('-', '_')}"
            )
            wallet_path = self._wallet_path(wallet_id)
            if wallet_path.exists():
                raise WorkspaceError(f"wallet_id {wallet_id!r} already exists")
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
                password=self.wallet_password,
            )
            tx = chain.queue_rotation(current_wallet=current_wallet, new_wallet=new_wallet)
            save_wallet(new_wallet, wallet_path)
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

    def _load_wallet(self, wallet_id: str, *, require_secret: bool = False):
        wallet = load_wallet(self._wallet_path(wallet_id), password=self.wallet_password)
        if not require_secret:
            return wallet

        try:
            _ = wallet.secret_key_bytes
        except ValueError as exc:
            raise WorkspaceError(
                "Wallet secret key is encrypted; set PQ_AGILE_CHAIN_WALLET_PASSWORD to enable signing"
            ) from exc
        return wallet

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

    @staticmethod
    def _chain_summary(chain: PQAgileChain | None) -> dict[str, Any] | None:
        if chain is None:
            return None

        latest_block = chain.blocks[-1] if chain.blocks else None
        return {
            "chain_version": chain.CHAIN_VERSION,
            "difficulty": chain.difficulty,
            "block_count": len(chain.blocks),
            "mempool_count": len(chain.mempool),
            "latest_block_index": latest_block.index if latest_block else None,
            "latest_block_hash": latest_block.block_hash if latest_block else None,
        }

    @staticmethod
    def _block_summary(block) -> dict[str, Any]:
        return {
            "index": block.index,
            "created_at": block.timestamp,
            "difficulty": block.difficulty,
            "nonce": block.nonce,
            "previous_hash": block.previous_hash,
            "block_hash": block.block_hash,
            "tx_count": len(block.transactions),
        }

    @staticmethod
    def _transaction_summary(
        tx: dict[str, Any],
        *,
        block_index: int | None,
        position: int | None,
        status: str,
    ) -> dict[str, Any]:
        summary = {
            "kind": tx["kind"],
            "created_at": tx.get("created_at"),
            "status": status,
            "block_index": block_index,
            "position": position,
            "nonce": tx.get("nonce"),
            "algo_id": tx.get("algo_id"),
        }
        for key in (
            "sender_account_id",
            "recipient_account_id",
            "account_id",
            "old_algo_id",
            "new_algo_id",
            "amount",
            "label",
        ):
            if key in tx:
                summary[key] = tx[key]
        return summary
