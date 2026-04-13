from __future__ import annotations

from pq_agile_chain.chain import ChainValidationError, PQAgileChain
from pq_agile_chain.crypto_backends import get_backend
from pq_agile_chain.models import TransferTx
from pq_agile_chain.utils import b64encode_bytes, utc_now
from pq_agile_chain.wallets import create_wallet


def _bootstrap_chain(*, difficulty: int = 1):
    alice = create_wallet(algo_id="ml-dsa-65", label="alice", security_floor=3)
    bob = create_wallet(algo_id="ml-dsa-65", label="bob", security_floor=3)
    chain = PQAgileChain.bootstrap(
        difficulty=difficulty,
        wallet_allocations=[(alice, 100), (bob, 0)],
    )
    return chain, alice, bob


def _signed_transfer(
    *,
    signing_wallet,
    claimed_sender_wallet,
    recipient_account_id: str,
    amount: int,
    nonce: int,
) -> TransferTx:
    tx = TransferTx(
        sender_account_id=claimed_sender_wallet.account_id,
        recipient_account_id=recipient_account_id,
        amount=amount,
        nonce=nonce,
        algo_id=claimed_sender_wallet.algo_id,
        public_key=claimed_sender_wallet.public_key,
        created_at=utc_now(),
    )
    backend = get_backend(signing_wallet.algo_id)
    tx.signature = b64encode_bytes(
        backend.sign(signing_wallet.secret_key_bytes, tx.signing_message())
    )
    return tx


def test_valid_transfer_and_chain_replay(tmp_path):
    chain, alice, bob = _bootstrap_chain()

    chain.queue_transfer(sender_wallet=alice, recipient_account_id=bob.account_id, amount=12)
    chain.mine_pending()
    chain.queue_transfer(sender_wallet=alice, recipient_account_id=bob.account_id, amount=8)
    chain.mine_pending()

    chain_path = tmp_path / "chain.json"
    chain.save(chain_path)
    reloaded = PQAgileChain.load(chain_path)
    final_state = reloaded.validate()

    assert len(reloaded.blocks) == 3
    assert final_state[alice.account_id].balance == 80
    assert final_state[alice.account_id].nonce == 2
    assert final_state[bob.account_id].balance == 20


def test_forged_signature_rejected():
    chain, alice, bob = _bootstrap_chain()
    forged = _signed_transfer(
        signing_wallet=bob,
        claimed_sender_wallet=alice,
        recipient_account_id=bob.account_id,
        amount=5,
        nonce=1,
    )

    try:
        chain.add_transaction(forged)
    except ChainValidationError as exc:
        assert "signature" in str(exc).lower()
    else:
        raise AssertionError("forged signature should have been rejected")


def test_nonce_reuse_rejected():
    chain, alice, bob = _bootstrap_chain()

    chain.queue_transfer(sender_wallet=alice, recipient_account_id=bob.account_id, amount=5)
    chain.mine_pending()

    replay = _signed_transfer(
        signing_wallet=alice,
        claimed_sender_wallet=alice,
        recipient_account_id=bob.account_id,
        amount=1,
        nonce=1,
    )

    try:
        chain.add_transaction(replay)
    except ChainValidationError as exc:
        assert "nonce" in str(exc).lower()
    else:
        raise AssertionError("nonce reuse should have been rejected")


def test_rotate_key_rejects_old_wallet_and_accepts_new_wallet():
    chain, alice, bob = _bootstrap_chain()
    alice_rotated = create_wallet(
        algo_id="sphincs-shake-256s-simple",
        label="alice-rotated",
        security_floor=5,
        account_id=alice.account_id,
    )

    chain.queue_rotation(current_wallet=alice, new_wallet=alice_rotated)
    chain.mine_pending()

    try:
        chain.queue_transfer(sender_wallet=alice, recipient_account_id=bob.account_id, amount=1)
    except ChainValidationError as exc:
        assert "active on-chain key" in str(exc)
    else:
        raise AssertionError("old wallet should be invalid after rotation")

    chain.queue_transfer(
        sender_wallet=alice_rotated, recipient_account_id=bob.account_id, amount=11
    )
    chain.mine_pending()
    final_state = chain.validate()

    assert final_state[alice.account_id].algo_id == "sphincs-shake-256s-simple"
    assert final_state[alice.account_id].security_floor == 5
    assert final_state[alice.account_id].balance == 89
    assert final_state[bob.account_id].balance == 11


def test_security_floor_blocks_downgrade():
    chain, alice, _bob = _bootstrap_chain()
    alice_rotated = create_wallet(
        algo_id="sphincs-shake-256s-simple",
        label="alice-rotated",
        security_floor=5,
        account_id=alice.account_id,
    )
    chain.queue_rotation(current_wallet=alice, new_wallet=alice_rotated)
    chain.mine_pending()

    downgrade_wallet = create_wallet(
        algo_id="ml-dsa-65",
        label="alice-downgrade",
        security_floor=3,
        account_id=alice.account_id,
    )

    try:
        chain.queue_rotation(current_wallet=alice_rotated, new_wallet=downgrade_wallet)
    except ChainValidationError as exc:
        assert "security_floor" in str(exc)
    else:
        raise AssertionError("downgrade below security_floor should be rejected")
