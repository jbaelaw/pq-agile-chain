# PQ-Agile Chain

`PQ-Agile Chain` is a small but runnable blockchain that uses real post-quantum signature schemes and adds a chain-level novelty: **on-chain cryptographic agility with enforced security floors**.

Instead of treating key migration as an off-chain operational detail, the chain stores each account's active algorithm, public key, nonce, and `security_floor`, then enforces key rotation through consensus rules.

## Why This Is Post-Quantum

This project does not invent its own signature primitive. It uses `pqcrypto`, which exposes tested bindings to PQClean implementations:

- `ml-dsa-65` for the default wallet/signing path
- `sphincs-shake-256s-simple` for upgrade and agility demonstrations

That means the "quantum-resistant" property comes from recognized post-quantum digital signature schemes, while the novelty comes from how the chain manages them.

## Novelty

The main novelty is **account-level PQ crypto agility as an on-chain rule**:

- Every account has an `account_id` distinct from its public key.
- The chain stores the currently active `algo_id`, `public_key`, `nonce`, `balance`, and `security_floor`.
- `RotateKeyTx` requires two proofs:
  - the old key authorizes the migration
  - the new key proves possession
- After a successful rotation, the old key is immediately invalid.
- Accounts cannot rotate to an algorithm below their current `security_floor`.

This creates a simple but meaningful distinction from a toy blockchain that merely signs transactions with a PQ signature.

More detail: [`docs/novelty.md`](docs/novelty.md)

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e .[dev]
.venv/bin/pq-agile-chain demo --workdir demo-output
```

The demo will:

- create two ML-DSA wallets
- initialize a chain with genesis balances
- send a transfer
- mine a block
- rotate Alice from `ml-dsa-65` to `sphincs-shake-256s-simple`
- mine the rotation
- send a transfer with the new key
- reject reuse of the old key
- reject a downgrade below `security_floor`
- validate the final chain

## Manual CLI Flow

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

Run the package without the console script:

```bash
PYTHONPATH=src .venv/bin/python -m pq_agile_chain demo --workdir demo-output
```

## Repository Layout

- `src/pq_agile_chain/crypto_backends.py`: PQ signature adapters and algorithm metadata
- `src/pq_agile_chain/models.py`: wallets, blocks, and transaction dataclasses
- `src/pq_agile_chain/chain.py`: replay-based validation, mempool handling, and novelty rules
- `src/pq_agile_chain/mining.py`: toy proof-of-work
- `src/pq_agile_chain/cli.py`: CLI entrypoints and demo
- `tests/test_chain.py`: focused regression tests
- `docs/novelty.md`: novelty explanation and threat model notes

## Limitations

- This is a toy blockchain, not a production network.
- Consensus is single-node file-based replay, not peer-to-peer networking.
- Proof-of-work is intentionally simple and not economically meaningful.
- Wallet files store secret keys unencrypted for simplicity.
- The chain currently supports only two PQ signature algorithms so the agility model is clear and testable.

## License

MIT
