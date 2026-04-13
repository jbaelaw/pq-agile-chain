from __future__ import annotations

import json
from pathlib import Path

from .crypto_backends import get_backend
from .models import WalletRecord
from .utils import b64encode_bytes, new_account_id, utc_now


def create_wallet(
    *,
    algo_id: str,
    label: str,
    security_floor: int | None = None,
    account_id: str | None = None,
) -> WalletRecord:
    backend = get_backend(algo_id)
    requested_floor = (
        backend.security_level if security_floor is None else security_floor
    )

    if requested_floor < 1:
        raise ValueError("security_floor must be at least 1")
    if requested_floor > backend.security_level:
        raise ValueError(
            f"{algo_id} only provides security level {backend.security_level}, "
            f"so security_floor cannot be {requested_floor}"
        )

    public_key, secret_key = backend.generate_keypair()
    return WalletRecord(
        account_id=account_id or new_account_id(),
        label=label,
        algo_id=algo_id,
        security_floor=requested_floor,
        public_key=b64encode_bytes(public_key),
        secret_key=b64encode_bytes(secret_key),
        created_at=utc_now(),
    )


def save_wallet(wallet: WalletRecord, path: str | Path) -> Path:
    wallet_path = Path(path)
    wallet_path.parent.mkdir(parents=True, exist_ok=True)
    wallet_path.write_text(json.dumps(wallet.to_dict(), indent=2) + "\n", encoding="utf-8")
    return wallet_path


def load_wallet(path: str | Path) -> WalletRecord:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return WalletRecord.from_dict(payload)
