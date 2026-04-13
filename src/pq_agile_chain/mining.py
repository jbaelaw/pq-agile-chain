from __future__ import annotations

from typing import Any

from .models import Block
from .utils import canonical_json_bytes, sha3_hex, utc_now


def compute_block_hash_payload(payload: dict[str, Any]) -> str:
    return sha3_hex(canonical_json_bytes(payload))


def compute_block_hash(block: Block) -> str:
    return compute_block_hash_payload(block.header_payload())


def has_valid_proof(block_hash: str, difficulty: int) -> bool:
    return block_hash.startswith("0" * difficulty)


def mine_block(
    *,
    index: int,
    previous_hash: str,
    difficulty: int,
    transactions: list[dict[str, Any]],
    timestamp: str | None = None,
) -> Block:
    mined_at = timestamp or utc_now()
    tx_payloads = [dict(payload) for payload in transactions]
    nonce = 0

    while True:
        header_payload = {
            "index": index,
            "previous_hash": previous_hash,
            "timestamp": mined_at,
            "difficulty": difficulty,
            "nonce": nonce,
            "transactions": tx_payloads,
        }
        block_hash = compute_block_hash_payload(header_payload)
        if has_valid_proof(block_hash, difficulty):
            return Block(
                index=index,
                previous_hash=previous_hash,
                timestamp=mined_at,
                difficulty=difficulty,
                nonce=nonce,
                transactions=tx_payloads,
                block_hash=block_hash,
            )
        nonce += 1
