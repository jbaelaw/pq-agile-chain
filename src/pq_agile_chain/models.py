from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .utils import b64decode_text, canonical_json_bytes


@dataclass(slots=True)
class WalletRecord:
    account_id: str
    label: str
    algo_id: str
    security_floor: int
    public_key: str
    secret_key: str
    created_at: str
    secret_key_format: str = "plain"
    secret_key_salt: str | None = None
    secret_key_nonce: str | None = None
    _cached_secret_key: bytes | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def is_encrypted(self) -> bool:
        return self.secret_key_format != "plain"

    @property
    def public_key_bytes(self) -> bytes:
        return b64decode_text(self.public_key)

    @property
    def secret_key_bytes(self) -> bytes:
        if self.is_encrypted:
            if self._cached_secret_key is None:
                raise ValueError("Wallet secret key is encrypted; unlock it first")
            return self._cached_secret_key
        return b64decode_text(self.secret_key)

    def unlock(self, password: str) -> None:
        from .wallets import decrypt_wallet_secret_key

        self._cached_secret_key = decrypt_wallet_secret_key(self, password)

    def lock(self) -> None:
        self._cached_secret_key = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "account_id": self.account_id,
            "label": self.label,
            "algo_id": self.algo_id,
            "security_floor": self.security_floor,
            "public_key": self.public_key,
            "secret_key": self.secret_key,
            "created_at": self.created_at,
        }
        if self.is_encrypted:
            payload["secret_key_format"] = self.secret_key_format
            payload["secret_key_salt"] = self.secret_key_salt
            payload["secret_key_nonce"] = self.secret_key_nonce
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WalletRecord:
        return cls(
            account_id=payload["account_id"],
            label=payload["label"],
            algo_id=payload["algo_id"],
            security_floor=int(payload["security_floor"]),
            public_key=payload["public_key"],
            secret_key=payload["secret_key"],
            created_at=payload["created_at"],
            secret_key_format=payload.get("secret_key_format", "plain"),
            secret_key_salt=payload.get("secret_key_salt"),
            secret_key_nonce=payload.get("secret_key_nonce"),
        )


@dataclass(slots=True)
class AccountState:
    account_id: str
    label: str
    algo_id: str
    public_key: str
    security_floor: int
    nonce: int
    balance: int

    def clone(self) -> AccountState:
        return AccountState(
            account_id=self.account_id,
            label=self.label,
            algo_id=self.algo_id,
            public_key=self.public_key,
            security_floor=self.security_floor,
            nonce=self.nonce,
            balance=self.balance,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "label": self.label,
            "algo_id": self.algo_id,
            "public_key": self.public_key,
            "security_floor": self.security_floor,
            "nonce": self.nonce,
            "balance": self.balance,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AccountState:
        return cls(
            account_id=payload["account_id"],
            label=payload["label"],
            algo_id=payload["algo_id"],
            public_key=payload["public_key"],
            security_floor=int(payload["security_floor"]),
            nonce=int(payload["nonce"]),
            balance=int(payload["balance"]),
        )


@dataclass(slots=True)
class GenesisAllocationTx:
    account_id: str
    label: str
    algo_id: str
    public_key: str
    security_floor: int
    balance: int
    kind: str = field(init=False, default="genesis_allocation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "account_id": self.account_id,
            "label": self.label,
            "algo_id": self.algo_id,
            "public_key": self.public_key,
            "security_floor": self.security_floor,
            "balance": self.balance,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GenesisAllocationTx:
        return cls(
            account_id=payload["account_id"],
            label=payload["label"],
            algo_id=payload["algo_id"],
            public_key=payload["public_key"],
            security_floor=int(payload["security_floor"]),
            balance=int(payload["balance"]),
        )


@dataclass(slots=True)
class TransferTx:
    sender_account_id: str
    recipient_account_id: str
    amount: int
    nonce: int
    algo_id: str
    public_key: str
    created_at: str
    signature: str = ""
    kind: str = field(init=False, default="transfer")

    def signing_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "sender_account_id": self.sender_account_id,
            "recipient_account_id": self.recipient_account_id,
            "amount": self.amount,
            "nonce": self.nonce,
            "algo_id": self.algo_id,
            "public_key": self.public_key,
            "created_at": self.created_at,
        }

    def signing_message(self) -> bytes:
        return canonical_json_bytes(
            {"domain": "pq_agile_chain.transfer.v1", "payload": self.signing_payload()}
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self.signing_payload()
        payload["signature"] = self.signature
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TransferTx:
        tx = cls(
            sender_account_id=payload["sender_account_id"],
            recipient_account_id=payload["recipient_account_id"],
            amount=int(payload["amount"]),
            nonce=int(payload["nonce"]),
            algo_id=payload["algo_id"],
            public_key=payload["public_key"],
            created_at=payload["created_at"],
            signature=payload.get("signature", ""),
        )
        return tx


@dataclass(slots=True)
class RotateKeyTx:
    account_id: str
    nonce: int
    old_algo_id: str
    old_public_key: str
    new_algo_id: str
    new_public_key: str
    requested_security_floor: int
    created_at: str
    old_signature: str = ""
    new_key_proof: str = ""
    kind: str = field(init=False, default="rotate_key")

    def base_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "account_id": self.account_id,
            "nonce": self.nonce,
            "old_algo_id": self.old_algo_id,
            "old_public_key": self.old_public_key,
            "new_algo_id": self.new_algo_id,
            "new_public_key": self.new_public_key,
            "requested_security_floor": self.requested_security_floor,
            "created_at": self.created_at,
        }

    def old_authorization_message(self) -> bytes:
        return canonical_json_bytes(
            {
                "domain": "pq_agile_chain.rotate.old.v1",
                "payload": self.base_payload(),
            }
        )

    def new_key_message(self) -> bytes:
        return canonical_json_bytes(
            {
                "domain": "pq_agile_chain.rotate.new.v1",
                "payload": self.base_payload(),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self.base_payload()
        payload["old_signature"] = self.old_signature
        payload["new_key_proof"] = self.new_key_proof
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RotateKeyTx:
        return cls(
            account_id=payload["account_id"],
            nonce=int(payload["nonce"]),
            old_algo_id=payload["old_algo_id"],
            old_public_key=payload["old_public_key"],
            new_algo_id=payload["new_algo_id"],
            new_public_key=payload["new_public_key"],
            requested_security_floor=int(payload["requested_security_floor"]),
            created_at=payload["created_at"],
            old_signature=payload.get("old_signature", ""),
            new_key_proof=payload.get("new_key_proof", ""),
        )


@dataclass(slots=True)
class Block:
    index: int
    previous_hash: str
    timestamp: str
    difficulty: int
    nonce: int
    transactions: list[dict[str, Any]]
    block_hash: str

    def header_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
            "transactions": self.transactions,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.header_payload()
        payload["block_hash"] = self.block_hash
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Block:
        return cls(
            index=int(payload["index"]),
            previous_hash=payload["previous_hash"],
            timestamp=payload["timestamp"],
            difficulty=int(payload["difficulty"]),
            nonce=int(payload["nonce"]),
            transactions=list(payload["transactions"]),
            block_hash=payload["block_hash"],
        )


Transaction = GenesisAllocationTx | TransferTx | RotateKeyTx


def transaction_from_dict(payload: dict[str, Any]) -> Transaction:
    kind = payload["kind"]
    if kind == "genesis_allocation":
        return GenesisAllocationTx.from_dict(payload)
    if kind == "transfer":
        return TransferTx.from_dict(payload)
    if kind == "rotate_key":
        return RotateKeyTx.from_dict(payload)
    raise ValueError(f"Unsupported transaction kind: {kind}")
