from __future__ import annotations

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
    assert {wallet["wallet_id"] for wallet in snapshot["wallets"]} == {"alice", "bob"}

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
