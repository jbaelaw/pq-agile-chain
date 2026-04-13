from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pq_agile_chain.web import create_app


def test_web_demo_flow(tmp_path):
    client = TestClient(create_app(tmp_path))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    bootstrap = client.post("/api/demo/bootstrap", json={"difficulty": 1})
    assert bootstrap.status_code == 200
    snapshot = bootstrap.json()["snapshot"]
    assert snapshot["workspace"]["has_chain"] is True
    assert snapshot["chain"]["block_count"] == 1
    assert {wallet["wallet_id"] for wallet in snapshot["wallets"]} == {"alice", "bob"}

    bootstrap_again = client.post("/api/demo/bootstrap", json={"difficulty": 1})
    assert bootstrap_again.status_code == 200

    blocks = client.get("/api/blocks?limit=2")
    assert blocks.status_code == 200
    assert blocks.json()["total"] == 1
    assert blocks.json()["items"][0]["index"] == 0

    transfer = client.post(
        "/api/transfer",
        json={
            "sender_wallet_id": "alice",
            "recipient_wallet_id": "bob",
            "amount": 7,
        },
    )
    assert transfer.status_code == 200
    assert len(transfer.json()["snapshot"]["mempool"]) == 1

    transactions = client.get("/api/transactions?limit=5")
    assert transactions.status_code == 200
    assert transactions.json()["items"][0]["status"] == "pending"

    mined = client.post("/api/mine")
    assert mined.status_code == 200
    assert mined.json()["block"]["index"] == 1

    rotate = client.post(
        "/api/rotate",
        json={
            "current_wallet_id": "alice",
            "new_algo_id": "sphincs-shake-256s-simple",
            "new_wallet_id": "alice-sphincs",
            "new_security_floor": 5,
        },
    )
    assert rotate.status_code == 200
    assert rotate.json()["wallet_id"] == "alice-sphincs"

    mined_rotation = client.post("/api/mine")
    assert mined_rotation.status_code == 200
    assert mined_rotation.json()["block"]["index"] == 2

    stale_transfer = client.post(
        "/api/transfer",
        json={
            "sender_wallet_id": "alice",
            "recipient_wallet_id": "bob",
            "amount": 1,
        },
    )
    assert stale_transfer.status_code == 400
    assert "active on-chain key" in stale_transfer.json()["detail"]

    fresh_transfer = client.post(
        "/api/transfer",
        json={
            "sender_wallet_id": "alice-sphincs",
            "recipient_wallet_id": "bob",
            "amount": 4,
        },
    )
    assert fresh_transfer.status_code == 200
    final_snapshot = fresh_transfer.json()["snapshot"]
    assert any(wallet["wallet_id"] == "alice-sphincs" for wallet in final_snapshot["wallets"])


def test_write_endpoints_can_require_admin_token(tmp_path, monkeypatch):
    monkeypatch.setenv("PQ_AGILE_CHAIN_ADMIN_TOKEN", "topsecret")
    client = TestClient(create_app(tmp_path))

    index = client.get("/")
    assert index.status_code == 200
    assert 'id="admin-token"' in index.text

    denied = client.post("/api/demo/bootstrap", json={"difficulty": 1})
    assert denied.status_code == 403

    allowed = client.post(
        "/api/demo/bootstrap",
        json={"difficulty": 1},
        headers={"X-Admin-Token": "topsecret"},
    )
    assert allowed.status_code == 200


def test_empty_admin_token_is_rejected_at_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("PQ_AGILE_CHAIN_ADMIN_TOKEN", "")

    with pytest.raises(ValueError, match="must not be empty"):
        create_app(tmp_path)


def test_rotate_rejects_existing_wallet_id(tmp_path):
    client = TestClient(create_app(tmp_path))
    bootstrap = client.post("/api/demo/bootstrap", json={"difficulty": 1})
    assert bootstrap.status_code == 200

    rotate = client.post(
        "/api/rotate",
        json={
            "current_wallet_id": "alice",
            "new_algo_id": "sphincs-shake-256s-simple",
            "new_wallet_id": "bob",
            "new_security_floor": 5,
        },
    )
    assert rotate.status_code == 400
    assert "already exists" in rotate.json()["detail"]


def test_invalid_rotate_backend_returns_client_error(tmp_path):
    client = TestClient(create_app(tmp_path))
    bootstrap = client.post("/api/demo/bootstrap", json={"difficulty": 1})
    assert bootstrap.status_code == 200

    rotate = client.post(
        "/api/rotate",
        json={
            "current_wallet_id": "alice",
            "new_algo_id": "not-a-real-backend",
            "new_wallet_id": "alice-invalid",
            "new_security_floor": 5,
        },
    )
    assert rotate.status_code == 400
    assert "Unsupported algorithm" in rotate.json()["detail"]


def test_web_workspace_can_use_encrypted_wallets(tmp_path, monkeypatch):
    monkeypatch.setenv("PQ_AGILE_CHAIN_WALLET_PASSWORD", "workspace-secret")
    client = TestClient(create_app(tmp_path))

    bootstrap = client.post("/api/demo/bootstrap", json={"difficulty": 1})
    assert bootstrap.status_code == 200
    wallet_payload = json.loads(
        (tmp_path / "wallets" / "alice.wallet.json").read_text(encoding="utf-8")
    )
    assert wallet_payload["secret_key_format"] == "scrypt-aes256-gcm-v1"

    transfer = client.post(
        "/api/transfer",
        json={
            "sender_wallet_id": "alice",
            "recipient_wallet_id": "bob",
            "amount": 3,
        },
    )
    assert transfer.status_code == 200
