# PQ-Agile Chain

`PQ-Agile Chain` is a small local blockchain demo built around real post-quantum signatures. Its main design point is that key rotation is part of the ledger rules rather than a wallet-side convention.

The chain tracks each account by a stable `account_id`. The active `algo_id`, `public_key`, `nonce`, `balance`, and `security_floor` live on-chain and are checked during replay.

## Cryptography

This project uses `pqcrypto` rather than implementing its own signature scheme. The current backends are:

- `ml-dsa-65`
- `sphincs-shake-256s-simple`

That keeps the post-quantum part tied to existing implementations while the chain logic focuses on how keys are managed over time.

## Key Rotation Rule

`RotateKeyTx` is valid only when:

- the current on-chain key signs the rotation request
- the replacement key proves possession
- the replacement algorithm meets the account's `security_floor`
- the floor is not lowered during the rotation

Once a rotation is mined, the previous key is no longer accepted for new transactions.

More detail: [`docs/novelty.md`](docs/novelty.md)

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pq-agile-chain demo --workdir demo-output
```

The demo creates two wallets, mines transfers, rotates one account from `ml-dsa-65` to `sphincs-shake-256s-simple`, then verifies that the old key and a downgrade attempt are both rejected.

## Web Explorer And API

Run the web app locally:

```bash
.venv/bin/pq-agile-chain-web
```

The server listens on `127.0.0.1:8401` by default. Open `http://127.0.0.1:8401/` to use the explorer.

Available endpoints:

- `GET /api/health`
- `GET /api/state`
- `POST /api/demo/bootstrap`
- `POST /api/transfer`
- `POST /api/rotate`
- `POST /api/mine`

The page is styled for `qc.jrti.org` and uses JRTI branding drawn from the main institute site.

## CLI Example

Create wallets:

```bash
.venv/bin/pq-agile-chain create-wallet --output wallets/alice.json --label alice --algo ml-dsa-65 --security-floor 3
.venv/bin/pq-agile-chain create-wallet --output wallets/bob.json --label bob --algo ml-dsa-65 --security-floor 3
```

Initialize genesis:

```bash
.venv/bin/pq-agile-chain init --chain chain.json --difficulty 2 --allocation wallets/alice.json=120 --allocation wallets/bob.json=25
```

Queue a transfer and mine it:

```bash
.venv/bin/pq-agile-chain transfer --chain chain.json --wallet wallets/alice.json --to-wallet wallets/bob.json --amount 15
.venv/bin/pq-agile-chain mine --chain chain.json
```

Rotate Alice to SPHINCS+ and mine the rotation:

```bash
.venv/bin/pq-agile-chain rotate-key --chain chain.json --wallet wallets/alice.json --new-wallet-out wallets/alice-rotated.json --new-algo sphincs-shake-256s-simple --new-security-floor 5
.venv/bin/pq-agile-chain mine --chain chain.json
```

Validate the chain:

```bash
.venv/bin/pq-agile-chain validate --chain chain.json
```

## Development

Run tests:

```bash
.venv/bin/pytest -q
```

Run the module directly:

```bash
PYTHONPATH=src .venv/bin/python -m pq_agile_chain demo --workdir demo-output
```

## Deployment

The repository now includes an Ubuntu/nginx deployment scaffold for `qc.jrti.org`:

- `deploy/nginx/qc.jrti.org.conf`
- `deploy/systemd/pq-agile-chain.service`
- `deploy/README.md`

The intended shape is:

1. `qc.jrti.org` resolves to the target server.
2. `systemd` runs `uvicorn` on `127.0.0.1:8401`.
3. `nginx` proxies `qc.jrti.org` to that local service.
4. `certbot` issues TLS once DNS is live.

## Repository Layout

- `src/pq_agile_chain/crypto_backends.py`: PQ signature adapters and algorithm metadata
- `src/pq_agile_chain/models.py`: wallets, blocks, and transaction dataclasses
- `src/pq_agile_chain/chain.py`: state replay, mempool handling, and validation rules
- `src/pq_agile_chain/mining.py`: simple proof-of-work
- `src/pq_agile_chain/cli.py`: command-line entry points
- `src/pq_agile_chain/service.py`: filesystem-backed workspace for the API
- `src/pq_agile_chain/web.py`: FastAPI app and browser explorer
- `tests/test_chain.py`: regression tests for replay, signatures, and key rotation
- `tests/test_web.py`: API and explorer smoke test
- `docs/novelty.md`: design note on the key rotation model

## Limits

- This is a single-node file-based demo, not a networked blockchain.
- The proof-of-work loop is intentionally simple.
- Wallet files store secret keys in plain JSON.
- Only two PQ signature backends are wired in today.
- `qc.jrti.org` still needs DNS and server access outside this repository.

## License

MIT
