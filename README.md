# PQ-Agile Chain

`PQ-Agile Chain` is an account-based blockchain demonstrator for studying post-quantum key rotation at the ledger layer. It uses `pqcrypto` for signature generation and verification, then makes key migration part of chain validation rather than a wallet-side convention.

The implementation keeps `account_id` stable across key changes. The active `algo_id`, `public_key`, `security_floor`, `nonce`, and `balance` are state variables derived by replaying the chain from genesis.

## What The Repository Implements

- account-based state, not UTXO
- deterministic transaction serialization
- replay-based validation from genesis on every load
- `genesis_allocation`, `transfer`, and `rotate_key` transactions
- fixed-difficulty proof-of-work for block creation
- CLI commands for encrypted wallet generation, transfers, mining, and key rotation
- FastAPI explorer and API behind `jrti.org/qc`

## Design Goal

The narrow question this repository answers is: how can a ledger accept post-quantum key replacement without treating the account itself as disposable?

The answer used here is straightforward:

- identity is a stable `account_id`
- signing material is replaceable state
- rotation is a first-class transaction type
- old and new keys both participate in authorization
- downgrade prevention is handled by a chain rule, not by operator discipline

This repository does not propose a new signature scheme or a new consensus protocol. It is a concrete reference implementation of one ledger-level rotation model.

## Ledger Model

### Account State

Each account stores:

- `account_id`
- `label`
- `algo_id`
- `public_key`
- `security_floor`
- `nonce`
- `balance`

### Transaction Types

`genesis_allocation`

- valid only in block `0`
- creates an initial account state and balance

`transfer`

- debits one existing account and credits another
- carries the sender's current `algo_id`, `public_key`, `nonce`, and signature

`rotate_key`

- keeps `account_id` unchanged
- replaces the active algorithm and public key for that account
- can optionally raise `security_floor`
- requires authorization from both the current key and the replacement key

### Block Structure

Each block stores:

- `index`
- `previous_hash`
- `timestamp`
- `difficulty`
- `nonce`
- `transactions`
- `block_hash`

`block_hash` is recomputed from the block header payload during replay and must satisfy the configured proof-of-work prefix rule.

## Validation Rules

Chain validation is replay-based. Loading a chain replays every block from genesis and recomputes account state.

`transfer` is accepted only if all of the following hold:

- the sender account exists
- the recipient account exists
- `amount > 0`
- `nonce == sender.nonce + 1`
- the presented `algo_id` matches the sender's active on-chain algorithm
- the presented `public_key` matches the sender's active on-chain key
- the signature verifies over the canonical transfer payload
- the sender has sufficient balance

`rotate_key` is accepted only if all of the following hold:

- the account exists
- `nonce == account.nonce + 1`
- the old algorithm and public key match the active on-chain key
- the old key signs the rotation authorization payload
- the new key signs a separate possession proof
- the rotation changes key material
- the new backend satisfies the current `security_floor`
- the requested floor does not lower the existing floor

Once a rotation is mined, the previous key is no longer valid for future transfers.

More detail: [`docs/novelty.md`](docs/novelty.md)

## Cryptographic Backends

This repository does not implement its own post-quantum signature primitive. It currently wraps:

- `pqcrypto.sign.ml_dsa_65`
- `pqcrypto.sign.ml_dsa_87`
- `pqcrypto.sign.falcon_512`
- `pqcrypto.sign.falcon_1024`
- `pqcrypto.sign.sphincs_shake_256s_simple`

The chain refers to those backends through the local ids:

- `ml-dsa-65`
- `ml-dsa-87`
- `falcon-512`
- `falcon-1024`
- `sphincs-shake-256s-simple`

`security_floor` is a repository-local policy value assigned in `src/pq_agile_chain/crypto_backends.py`. In this codebase it is used to block configured downgrade paths. It should be read as an application rule for this demonstrator, not as a stand-alone cryptographic claim beyond the backend mapping configured here.

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export PQ_AGILE_CHAIN_WALLET_PASSWORD='change-me-if-you-want-encrypted-wallets'
.venv/bin/pq-agile-chain demo --workdir demo-output
```

The built-in demo performs the following sequence:

- create two `ml-dsa-65` wallets
- initialize a genesis block
- submit and mine a transfer
- rotate one account to `sphincs-shake-256s-simple`
- mine the rotation
- verify that the old key is rejected
- verify that a downgrade below `security_floor` is rejected

## CLI Workflow

Create wallets:

```bash
export PQ_AGILE_CHAIN_WALLET_PASSWORD='change-me-if-you-want-encrypted-wallets'
.venv/bin/pq-agile-chain create-wallet --output wallets/alice.json --label alice --algo ml-dsa-65 --security-floor 3 --password-env PQ_AGILE_CHAIN_WALLET_PASSWORD
.venv/bin/pq-agile-chain create-wallet --output wallets/bob.json --label bob --algo ml-dsa-65 --security-floor 3 --password-env PQ_AGILE_CHAIN_WALLET_PASSWORD
```

Initialize genesis:

```bash
.venv/bin/pq-agile-chain init --chain chain.json --difficulty 2 --allocation wallets/alice.json=120 --allocation wallets/bob.json=25
```

Queue a transfer and mine it:

```bash
.venv/bin/pq-agile-chain transfer --chain chain.json --wallet wallets/alice.json --wallet-password-env PQ_AGILE_CHAIN_WALLET_PASSWORD --to-wallet wallets/bob.json --amount 15
.venv/bin/pq-agile-chain mine --chain chain.json
```

Rotate Alice to a different backend and mine the rotation:

```bash
.venv/bin/pq-agile-chain rotate-key --chain chain.json --wallet wallets/alice.json --wallet-password-env PQ_AGILE_CHAIN_WALLET_PASSWORD --new-wallet-out wallets/alice-rotated.json --new-wallet-password-env PQ_AGILE_CHAIN_WALLET_PASSWORD --new-algo sphincs-shake-256s-simple --new-security-floor 5
.venv/bin/pq-agile-chain mine --chain chain.json
```

Replay and validate the chain:

```bash
.venv/bin/pq-agile-chain validate --chain chain.json
```

## Web Explorer And API

Run the web app locally:

```bash
.venv/bin/pq-agile-chain-web
```

By default the service listens on `127.0.0.1:8401`.

API surface:

- `GET /api/health`: liveness check
- `GET /api/state`: current chain summary, wallet list, account list, and mempool snapshot
- `GET /api/blocks`: paginated block summaries
- `GET /api/transactions`: paginated transaction summaries
- `POST /api/demo/bootstrap`: reset the local workspace and create a fresh demo chain
- `POST /api/transfer`: enqueue a signed transfer
- `POST /api/rotate`: enqueue a key rotation and create the replacement wallet file
- `POST /api/mine`: mine the current mempool into the next block

If `PQ_AGILE_CHAIN_ADMIN_TOKEN` is set, the write endpoints require `X-Admin-Token` or `Authorization: Bearer ...`. The bundled browser explorer includes a session-local token field and will forward that value on write requests.

If `PQ_AGILE_CHAIN_WALLET_PASSWORD` is set, demo and workspace wallets are stored encrypted at rest and unlocked inside the service for signing operations.

The deployed explorer runs at `jrti.org/qc`. In the current deployment that path may also be protected at the nginx layer.

## Verification

Run tests:

```bash
.venv/bin/pytest -q
```

The test suite currently covers:

- valid transfer replay
- forged signature rejection
- nonce reuse rejection
- stale-key rejection after rotation
- `security_floor` downgrade rejection
- repeated web bootstrap of the same workspace
- encrypted wallet round-trip and signing
- expanded PQ backend smoke coverage
- write-endpoint token enforcement

## Deployment

The repository includes an Ubuntu plus `systemd` plus `nginx` deployment scaffold for `jrti.org/qc`:

- `deploy/systemd/pq-agile-chain.service`
- `deploy/nginx/jrti.org-qc.conf`
- `deploy/README.md`

The intended shape is:

1. `uvicorn` binds to `127.0.0.1:8401`
2. the existing `jrti.org` nginx vhost includes the `/qc` snippet
3. nginx proxies `/qc/` to the local FastAPI process
4. nginx can restrict network access, and the application can separately require `PQ_AGILE_CHAIN_ADMIN_TOKEN` for write operations

## Repository Layout

- `src/pq_agile_chain/crypto_backends.py`: backend registry and signing adapters
- `src/pq_agile_chain/models.py`: wallet, transaction, block, and state dataclasses
- `src/pq_agile_chain/chain.py`: replay engine and validation rules
- `src/pq_agile_chain/mining.py`: proof-of-work loop and block hashing
- `src/pq_agile_chain/cli.py`: command-line interface
- `src/pq_agile_chain/service.py`: filesystem-backed workspace used by the web API
- `src/pq_agile_chain/web.py`: FastAPI application and browser explorer
- `tests/test_chain.py`: chain-level regression tests
- `tests/test_web.py`: API smoke test and workspace reset test
- `docs/novelty.md`: technical note on the rotation model

## Current Scope And Limits

- This is a single-node local state machine. It does not implement peer discovery, block propagation, fork choice between competing nodes, or Byzantine consensus.
- Proof-of-work is intentionally minimal: fixed difficulty, no retargeting, no timestamp discipline, no miner rewards, and no economic security model.
- Wallet files can now be encrypted at rest with `scrypt` plus AES-GCM, but there is still no mnemonic format, HSM integration, or hardware wallet path.
- `security_floor` is a local policy integer attached to configured backends in this repository. It is useful for downgrade prevention inside this demo, but it is not a substitute for a formal external security evaluation.
- The backend registry is still small and policy-driven. Adding more PQ schemes still requires code changes and explicit decisions about how local `security_floor` values are assigned.
- State is still kept in JSON files and replayed in memory. Block and transaction reads now have paginated API endpoints, but there is still no database, no secondary indexing layer, and no pruning for large histories.
- The write API mutates local filesystem state. Application-level token gating is supported now, but a public deployment should still pair it with network-level controls such as the current nginx restrictions.
- The explorer is an operational view over one workspace, not a multi-tenant block explorer for arbitrary chains.

## License

MIT
