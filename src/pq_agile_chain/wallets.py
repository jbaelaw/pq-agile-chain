from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .crypto_backends import get_backend
from .models import WalletRecord
from .utils import b64decode_text, b64encode_bytes, new_account_id, utc_now

_SECRET_KEY_FORMAT = "scrypt-aes256-gcm-v1"
_KDF_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32


def resolve_wallet_password(
    *,
    password: str | None = None,
    password_env: str | None = None,
    default_env: str | None = None,
) -> str | None:
    if password is not None:
        if not password:
            raise ValueError("Wallet password must not be empty")
        return password

    if password_env is not None:
        value = os.environ.get(password_env)
        if value is None:
            raise ValueError(f"Environment variable {password_env!r} is not set")
        if not value:
            raise ValueError(f"Environment variable {password_env!r} is empty")
        return value

    if default_env is None:
        return None

    value = os.environ.get(default_env)
    if value == "":
        raise ValueError(f"Environment variable {default_env!r} is empty")
    return value


def _derive_wallet_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**15,
        r=8,
        p=1,
        dklen=_KEY_LEN,
        maxmem=64 * 1024 * 1024,
    )


def encrypt_wallet_secret_key(secret_key: bytes, password: str) -> tuple[str, str, str]:
    salt = os.urandom(_KDF_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_wallet_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, secret_key, None)
    return (
        b64encode_bytes(ciphertext),
        b64encode_bytes(salt),
        b64encode_bytes(nonce),
    )


def decrypt_wallet_secret_key(wallet: WalletRecord, password: str) -> bytes:
    if wallet.secret_key_format == "plain":
        return b64decode_text(wallet.secret_key)
    if wallet.secret_key_format != _SECRET_KEY_FORMAT:
        raise ValueError(
            f"Unsupported wallet secret key format: {wallet.secret_key_format!r}"
        )
    if wallet.secret_key_salt is None or wallet.secret_key_nonce is None:
        raise ValueError("Encrypted wallet is missing salt or nonce metadata")

    salt = b64decode_text(wallet.secret_key_salt)
    nonce = b64decode_text(wallet.secret_key_nonce)
    ciphertext = b64decode_text(wallet.secret_key)
    key = _derive_wallet_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError("Failed to decrypt wallet secret key") from exc


def create_wallet(
    *,
    algo_id: str,
    label: str,
    security_floor: int | None = None,
    account_id: str | None = None,
    password: str | None = None,
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
    secret_key_payload = b64encode_bytes(secret_key)
    secret_key_format = "plain"
    secret_key_salt: str | None = None
    secret_key_nonce: str | None = None
    if password is not None:
        secret_key_payload, secret_key_salt, secret_key_nonce = encrypt_wallet_secret_key(
            secret_key,
            password,
        )
        secret_key_format = _SECRET_KEY_FORMAT

    return WalletRecord(
        account_id=account_id or new_account_id(),
        label=label,
        algo_id=algo_id,
        security_floor=requested_floor,
        public_key=b64encode_bytes(public_key),
        secret_key=secret_key_payload,
        created_at=utc_now(),
        secret_key_format=secret_key_format,
        secret_key_salt=secret_key_salt,
        secret_key_nonce=secret_key_nonce,
        _cached_secret_key=secret_key,
    )


def save_wallet(wallet: WalletRecord, path: str | Path) -> Path:
    wallet_path = Path(path)
    wallet_path.parent.mkdir(parents=True, exist_ok=True)
    wallet_path.write_text(json.dumps(wallet.to_dict(), indent=2) + "\n", encoding="utf-8")
    return wallet_path


def load_wallet(path: str | Path, password: str | None = None) -> WalletRecord:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    wallet = WalletRecord.from_dict(payload)
    if password is not None:
        wallet.unlock(password)
    return wallet
