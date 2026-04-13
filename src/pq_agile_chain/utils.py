from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_json_bytes(payload: Any) -> bytes:
    return canonical_json(payload).encode("utf-8")


def sha3_hex(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


def sha3_hex_payload(payload: Any) -> str:
    return sha3_hex(canonical_json_bytes(payload))


def b64encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def b64decode_text(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def new_account_id() -> str:
    return f"acct_{uuid.uuid4().hex[:24]}"
