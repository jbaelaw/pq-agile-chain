from __future__ import annotations

import json

import pytest

from pq_agile_chain.chain import PQAgileChain
from pq_agile_chain.crypto_backends import get_backend
from pq_agile_chain.wallets import create_wallet, load_wallet, save_wallet


def test_encrypted_wallet_round_trip_supports_signing(tmp_path):
    alice = create_wallet(
        algo_id="ml-dsa-65",
        label="alice",
        security_floor=3,
        password="correct horse battery staple",
    )
    bob = create_wallet(algo_id="ml-dsa-65", label="bob", security_floor=3)
    wallet_path = save_wallet(alice, tmp_path / "alice.wallet.json")

    on_disk = json.loads(wallet_path.read_text(encoding="utf-8"))
    assert on_disk["secret_key_format"] == "scrypt-aes256-gcm-v1"
    assert on_disk["secret_key"] != alice.secret_key_bytes.decode("latin1", errors="ignore")

    locked_wallet = load_wallet(wallet_path)
    with pytest.raises(ValueError, match="unlock it first"):
        _ = locked_wallet.secret_key_bytes

    with pytest.raises(ValueError, match="decrypt"):
        load_wallet(wallet_path, password="wrong password")

    unlocked_wallet = load_wallet(wallet_path, password="correct horse battery staple")
    chain = PQAgileChain.bootstrap(
        difficulty=1,
        wallet_allocations=[(unlocked_wallet, 25), (bob, 0)],
    )

    tx = chain.queue_transfer(
        sender_wallet=unlocked_wallet,
        recipient_account_id=bob.account_id,
        amount=7,
    )
    assert tx.amount == 7


@pytest.mark.parametrize("algo_id", ["ml-dsa-87", "falcon-512", "falcon-1024"])
def test_additional_signature_backends_sign_and_verify(algo_id: str):
    wallet = create_wallet(algo_id=algo_id, label=algo_id, security_floor=1)
    backend = get_backend(algo_id)
    message = b"pq-agile-chain backend smoke test"

    signature = backend.sign(wallet.secret_key_bytes, message)

    assert backend.verify(wallet.public_key_bytes, message, signature) is True
