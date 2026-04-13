from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .crypto_backends import get_backend, security_level
from .mining import compute_block_hash, has_valid_proof, mine_block
from .models import (
    AccountState,
    Block,
    GenesisAllocationTx,
    RotateKeyTx,
    Transaction,
    TransferTx,
    WalletRecord,
    transaction_from_dict,
)
from .utils import b64decode_text, b64encode_bytes, utc_now


class ChainValidationError(RuntimeError):
    """Raised when the chain, a block, or a transaction is invalid."""


def _require_nonnegative_amount(amount: int) -> None:
    if amount < 0:
        raise ChainValidationError("Amounts must be non-negative")


def _make_state(wallet: WalletRecord, balance: int) -> GenesisAllocationTx:
    _require_nonnegative_amount(balance)
    return GenesisAllocationTx(
        account_id=wallet.account_id,
        label=wallet.label,
        algo_id=wallet.algo_id,
        public_key=wallet.public_key,
        security_floor=wallet.security_floor,
        balance=balance,
    )


class PQAgileChain:
    CHAIN_VERSION = "pq-agile-chain-v1"

    def __init__(
        self,
        *,
        difficulty: int,
        blocks: list[Block] | None = None,
        mempool: list[dict] | None = None,
    ) -> None:
        self.difficulty = difficulty
        self.blocks = blocks or []
        self.mempool = mempool or []

    @classmethod
    def bootstrap(
        cls,
        *,
        difficulty: int,
        wallet_allocations: Iterable[tuple[WalletRecord, int]],
    ) -> PQAgileChain:
        allocations = [_make_state(wallet, balance) for wallet, balance in wallet_allocations]
        if not allocations:
            raise ChainValidationError("At least one genesis allocation is required")

        account_ids = [allocation.account_id for allocation in allocations]
        if len(account_ids) != len(set(account_ids)):
            raise ChainValidationError("Duplicate account_id values in genesis allocations")

        genesis_block = mine_block(
            index=0,
            previous_hash="0" * 64,
            difficulty=difficulty,
            transactions=[allocation.to_dict() for allocation in allocations],
        )
        return cls(difficulty=difficulty, blocks=[genesis_block], mempool=[])

    @classmethod
    def load(cls, path: str | Path) -> PQAgileChain:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        blocks = [Block.from_dict(item) for item in payload["blocks"]]
        mempool = list(payload.get("mempool", []))
        return cls(difficulty=int(payload["difficulty"]), blocks=blocks, mempool=mempool)

    def save(self, path: str | Path) -> Path:
        chain_path = Path(path)
        chain_path.parent.mkdir(parents=True, exist_ok=True)
        chain_path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return chain_path

    def to_dict(self) -> dict:
        return {
            "chain_version": self.CHAIN_VERSION,
            "difficulty": self.difficulty,
            "blocks": [block.to_dict() for block in self.blocks],
            "mempool": [dict(payload) for payload in self.mempool],
        }

    def committed_state(self) -> dict[str, AccountState]:
        return self._replay(include_mempool=False)

    def projected_state(self) -> dict[str, AccountState]:
        return self._replay(include_mempool=True)

    def queue_transfer(
        self,
        *,
        sender_wallet: WalletRecord,
        recipient_account_id: str,
        amount: int,
    ) -> TransferTx:
        if amount <= 0:
            raise ChainValidationError("Transfer amount must be positive")

        state = self.projected_state()
        sender_state = self._require_account(state, sender_wallet.account_id)
        if sender_state.algo_id != sender_wallet.algo_id or sender_state.public_key != sender_wallet.public_key:
            raise ChainValidationError(
                "Sender wallet does not match the currently active on-chain key"
            )

        tx = TransferTx(
            sender_account_id=sender_wallet.account_id,
            recipient_account_id=recipient_account_id,
            amount=amount,
            nonce=sender_state.nonce + 1,
            algo_id=sender_wallet.algo_id,
            public_key=sender_wallet.public_key,
            created_at=utc_now(),
        )
        backend = get_backend(sender_wallet.algo_id)
        tx.signature = b64encode_bytes(
            backend.sign(sender_wallet.secret_key_bytes, tx.signing_message())
        )
        self.add_transaction(tx)
        return tx

    def queue_rotation(
        self,
        *,
        current_wallet: WalletRecord,
        new_wallet: WalletRecord,
    ) -> RotateKeyTx:
        if current_wallet.account_id != new_wallet.account_id:
            raise ChainValidationError("Rotation must keep the same account_id")

        state = self.projected_state()
        current_state = self._require_account(state, current_wallet.account_id)
        if (
            current_state.algo_id != current_wallet.algo_id
            or current_state.public_key != current_wallet.public_key
        ):
            raise ChainValidationError(
                "Current wallet does not match the currently active on-chain key"
            )

        tx = RotateKeyTx(
            account_id=current_wallet.account_id,
            nonce=current_state.nonce + 1,
            old_algo_id=current_wallet.algo_id,
            old_public_key=current_wallet.public_key,
            new_algo_id=new_wallet.algo_id,
            new_public_key=new_wallet.public_key,
            requested_security_floor=new_wallet.security_floor,
            created_at=utc_now(),
        )
        old_backend = get_backend(current_wallet.algo_id)
        new_backend = get_backend(new_wallet.algo_id)
        tx.old_signature = b64encode_bytes(
            old_backend.sign(current_wallet.secret_key_bytes, tx.old_authorization_message())
        )
        tx.new_key_proof = b64encode_bytes(
            new_backend.sign(new_wallet.secret_key_bytes, tx.new_key_message())
        )
        self.add_transaction(tx)
        return tx

    def add_transaction(self, tx: Transaction) -> None:
        if isinstance(tx, GenesisAllocationTx):
            raise ChainValidationError("Genesis allocations can only appear in block 0")

        state = self.projected_state()
        self._apply_transaction(state, tx, in_genesis_block=False)
        self.mempool.append(tx.to_dict())

    def mine_pending(self) -> Block:
        if not self.mempool:
            raise ChainValidationError("No pending transactions to mine")

        preview_state = self.committed_state()
        for payload in self.mempool:
            self._apply_transaction(preview_state, transaction_from_dict(payload), False)

        block = mine_block(
            index=len(self.blocks),
            previous_hash=self.blocks[-1].block_hash,
            difficulty=self.difficulty,
            transactions=self.mempool,
        )
        self.blocks.append(block)
        self.mempool = []
        return block

    def validate(self) -> dict[str, AccountState]:
        return self._replay(include_mempool=False)

    def account_snapshots(self, *, include_mempool: bool = False) -> list[dict]:
        state = self.projected_state() if include_mempool else self.committed_state()
        return [state[account_id].to_dict() for account_id in sorted(state)]

    def _replay(self, *, include_mempool: bool) -> dict[str, AccountState]:
        if not self.blocks:
            raise ChainValidationError("Chain is empty")

        state: dict[str, AccountState] = {}
        expected_prev_hash = "0" * 64

        for expected_index, block in enumerate(self.blocks):
            self._validate_block_header(
                block=block,
                expected_index=expected_index,
                expected_prev_hash=expected_prev_hash,
            )
            for payload in block.transactions:
                tx = transaction_from_dict(payload)
                self._apply_transaction(state, tx, in_genesis_block=expected_index == 0)
            expected_prev_hash = block.block_hash

        if include_mempool:
            for payload in self.mempool:
                tx = transaction_from_dict(payload)
                self._apply_transaction(state, tx, in_genesis_block=False)

        return {account_id: account.clone() for account_id, account in state.items()}

    def _validate_block_header(
        self,
        *,
        block: Block,
        expected_index: int,
        expected_prev_hash: str,
    ) -> None:
        if block.index != expected_index:
            raise ChainValidationError(
                f"Block index mismatch: expected {expected_index}, got {block.index}"
            )
        if block.previous_hash != expected_prev_hash:
            raise ChainValidationError(
                f"Block {block.index} previous hash does not match the prior block"
            )
        if block.difficulty != self.difficulty:
            raise ChainValidationError(
                f"Block {block.index} difficulty changed unexpectedly"
            )
        computed_hash = compute_block_hash(block)
        if computed_hash != block.block_hash:
            raise ChainValidationError(f"Block {block.index} hash mismatch")
        if not has_valid_proof(block.block_hash, block.difficulty):
            raise ChainValidationError(f"Block {block.index} does not satisfy proof-of-work")

    def _apply_transaction(
        self,
        state: dict[str, AccountState],
        tx: Transaction,
        in_genesis_block: bool,
    ) -> None:
        if isinstance(tx, GenesisAllocationTx):
            if not in_genesis_block:
                raise ChainValidationError("Genesis allocations are only valid in block 0")
            self._apply_genesis_allocation(state, tx)
            return

        if in_genesis_block:
            raise ChainValidationError("Non-genesis transactions are not allowed in block 0")

        if isinstance(tx, TransferTx):
            self._apply_transfer(state, tx)
            return

        if isinstance(tx, RotateKeyTx):
            self._apply_rotation(state, tx)
            return

        raise ChainValidationError(f"Unsupported transaction type: {type(tx).__name__}")

    def _apply_genesis_allocation(
        self, state: dict[str, AccountState], tx: GenesisAllocationTx
    ) -> None:
        _require_nonnegative_amount(tx.balance)
        if tx.account_id in state:
            raise ChainValidationError(f"Duplicate genesis allocation for {tx.account_id}")
        state[tx.account_id] = AccountState(
            account_id=tx.account_id,
            label=tx.label,
            algo_id=tx.algo_id,
            public_key=tx.public_key,
            security_floor=tx.security_floor,
            nonce=0,
            balance=tx.balance,
        )

    def _apply_transfer(self, state: dict[str, AccountState], tx: TransferTx) -> None:
        if tx.amount <= 0:
            raise ChainValidationError("Transfer amount must be positive")

        sender = self._require_account(state, tx.sender_account_id)
        recipient = self._require_account(state, tx.recipient_account_id)

        if tx.nonce != sender.nonce + 1:
            raise ChainValidationError(
                f"Invalid nonce for {tx.sender_account_id}: expected {sender.nonce + 1}, got {tx.nonce}"
            )
        if tx.algo_id != sender.algo_id:
            raise ChainValidationError("Transfer signed with the wrong algorithm for the account")
        if tx.public_key != sender.public_key:
            raise ChainValidationError("Transfer signed with a stale or unauthorized public key")

        backend = get_backend(tx.algo_id)
        if not backend.verify(
            b64decode_text(tx.public_key),
            tx.signing_message(),
            b64decode_text(tx.signature),
        ):
            raise ChainValidationError("Transfer signature verification failed")

        if sender.balance < tx.amount:
            raise ChainValidationError("Insufficient balance for transfer")

        sender.balance -= tx.amount
        recipient.balance += tx.amount
        sender.nonce = tx.nonce

    def _apply_rotation(self, state: dict[str, AccountState], tx: RotateKeyTx) -> None:
        account = self._require_account(state, tx.account_id)

        if tx.nonce != account.nonce + 1:
            raise ChainValidationError(
                f"Invalid nonce for rotation on {tx.account_id}: expected {account.nonce + 1}, got {tx.nonce}"
            )
        if tx.old_algo_id != account.algo_id:
            raise ChainValidationError("Rotation old algorithm does not match on-chain state")
        if tx.old_public_key != account.public_key:
            raise ChainValidationError("Rotation old key does not match the active on-chain key")

        new_algo_security = security_level(tx.new_algo_id)
        if new_algo_security < account.security_floor:
            raise ChainValidationError(
                f"Rotation to {tx.new_algo_id} violates security_floor={account.security_floor}"
            )
        if tx.requested_security_floor < account.security_floor:
            raise ChainValidationError("security_floor cannot be lowered during rotation")
        if tx.requested_security_floor > new_algo_security:
            raise ChainValidationError(
                "requested security_floor exceeds the new algorithm's security level"
            )
        if tx.new_algo_id == tx.old_algo_id and tx.new_public_key == tx.old_public_key:
            raise ChainValidationError("Rotation must change the active key material")

        old_backend = get_backend(tx.old_algo_id)
        if not old_backend.verify(
            b64decode_text(tx.old_public_key),
            tx.old_authorization_message(),
            b64decode_text(tx.old_signature),
        ):
            raise ChainValidationError("Old-key authorization for rotation failed")

        new_backend = get_backend(tx.new_algo_id)
        if not new_backend.verify(
            b64decode_text(tx.new_public_key),
            tx.new_key_message(),
            b64decode_text(tx.new_key_proof),
        ):
            raise ChainValidationError("New-key ownership proof for rotation failed")

        account.algo_id = tx.new_algo_id
        account.public_key = tx.new_public_key
        account.security_floor = tx.requested_security_floor
        account.nonce = tx.nonce

    @staticmethod
    def _require_account(
        state: dict[str, AccountState], account_id: str
    ) -> AccountState:
        try:
            return state[account_id]
        except KeyError as exc:
            raise ChainValidationError(f"Unknown account: {account_id}") from exc
