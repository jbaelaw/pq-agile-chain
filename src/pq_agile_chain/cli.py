from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .chain import ChainValidationError, PQAgileChain
from .crypto_backends import DEFAULT_ALGO_ID, supported_algorithms
from .wallets import create_wallet, load_wallet, resolve_wallet_password, save_wallet

DEFAULT_WALLET_PASSWORD_ENV = "PQ_AGILE_CHAIN_WALLET_PASSWORD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pq-agile-chain",
        description="Local blockchain demo with post-quantum key rotation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_wallet_parser = subparsers.add_parser(
        "create-wallet", help="Generate a PQ wallet file"
    )
    create_wallet_parser.add_argument("--output", required=True, help="Wallet JSON path")
    create_wallet_parser.add_argument("--label", required=True, help="Human-friendly label")
    create_wallet_parser.add_argument(
        "--algo", default=DEFAULT_ALGO_ID, choices=supported_algorithms()
    )
    create_wallet_parser.add_argument(
        "--security-floor",
        type=int,
        default=None,
        help="Minimum future algorithm security level this account will accept",
    )
    create_wallet_parser.add_argument(
        "--password",
        default=None,
        help="Encrypt the wallet secret key with this password",
    )
    create_wallet_parser.add_argument(
        "--password-env",
        default=None,
        help="Read the wallet encryption password from this environment variable",
    )

    init_parser = subparsers.add_parser("init", help="Create a genesis chain file")
    init_parser.add_argument("--chain", required=True, help="Chain JSON path")
    init_parser.add_argument(
        "--difficulty", type=int, default=2, help="Proof-of-work difficulty"
    )
    init_parser.add_argument(
        "--allocation",
        action="append",
        required=True,
        help="Genesis allocation in the form wallet.json=amount",
    )

    transfer_parser = subparsers.add_parser(
        "transfer", help="Queue a signed transfer into the mempool"
    )
    transfer_parser.add_argument("--chain", required=True, help="Chain JSON path")
    transfer_parser.add_argument("--wallet", required=True, help="Sender wallet path")
    transfer_parser.add_argument(
        "--wallet-password",
        default=None,
        help="Password used to unlock the sender wallet",
    )
    transfer_parser.add_argument(
        "--wallet-password-env",
        default=None,
        help="Read the sender wallet password from this environment variable",
    )
    transfer_recipient = transfer_parser.add_mutually_exclusive_group(required=True)
    transfer_recipient.add_argument("--to-wallet", help="Recipient wallet path")
    transfer_recipient.add_argument("--to-account", help="Recipient account_id")
    transfer_parser.add_argument("--amount", required=True, type=int)

    rotate_parser = subparsers.add_parser(
        "rotate-key", help="Queue a PQ algorithm/key rotation transaction"
    )
    rotate_parser.add_argument("--chain", required=True, help="Chain JSON path")
    rotate_parser.add_argument("--wallet", required=True, help="Current wallet path")
    rotate_parser.add_argument(
        "--wallet-password",
        default=None,
        help="Password used to unlock the current wallet",
    )
    rotate_parser.add_argument(
        "--wallet-password-env",
        default=None,
        help="Read the current wallet password from this environment variable",
    )
    rotate_parser.add_argument(
        "--new-wallet-out", required=True, help="Where to write the rotated wallet"
    )
    rotate_parser.add_argument(
        "--new-algo", required=True, choices=supported_algorithms()
    )
    rotate_parser.add_argument(
        "--new-security-floor",
        type=int,
        default=None,
        help="New security floor. Defaults to the current floor.",
    )
    rotate_parser.add_argument(
        "--new-label",
        default=None,
        help="Optional new wallet label. Defaults to '<old>-rotated'.",
    )
    rotate_parser.add_argument(
        "--new-wallet-password",
        default=None,
        help="Password used to encrypt the replacement wallet",
    )
    rotate_parser.add_argument(
        "--new-wallet-password-env",
        default=None,
        help="Read the replacement wallet password from this environment variable",
    )

    mine_parser = subparsers.add_parser("mine", help="Mine the current mempool")
    mine_parser.add_argument("--chain", required=True, help="Chain JSON path")

    validate_parser = subparsers.add_parser("validate", help="Replay and validate the chain")
    validate_parser.add_argument("--chain", required=True, help="Chain JSON path")

    demo_parser = subparsers.add_parser("demo", help="Run the built-in scenario")
    demo_parser.add_argument(
        "--workdir", default="demo-output", help="Directory for demo artifacts"
    )
    demo_parser.add_argument(
        "--difficulty", type=int, default=2, help="Proof-of-work difficulty"
    )
    demo_parser.add_argument(
        "--wallet-password",
        default=None,
        help="Password used to encrypt demo wallets",
    )
    demo_parser.add_argument(
        "--wallet-password-env",
        default=None,
        help="Read the demo wallet password from this environment variable",
    )

    return parser


def _parse_allocation(spec: str) -> tuple[str, int]:
    wallet_path, sep, amount_text = spec.partition("=")
    if not sep:
        raise ValueError(f"Invalid allocation '{spec}'. Expected wallet.json=amount")
    amount = int(amount_text)
    if amount < 0:
        raise ValueError("Genesis allocations must be non-negative")
    return wallet_path, amount


def _load_wallet_for_signing(
    wallet_path: str,
    *,
    password: str | None = None,
    password_env: str | None = None,
) -> object:
    resolved_password = resolve_wallet_password(
        password=password,
        password_env=password_env,
        default_env=DEFAULT_WALLET_PASSWORD_ENV,
    )
    return load_wallet(wallet_path, password=resolved_password)


def cmd_create_wallet(args: argparse.Namespace) -> int:
    wallet_password = resolve_wallet_password(
        password=args.password,
        password_env=args.password_env,
    )
    wallet = create_wallet(
        algo_id=args.algo,
        label=args.label,
        security_floor=args.security_floor,
        password=wallet_password,
    )
    save_wallet(wallet, args.output)
    storage_mode = "encrypted" if wallet.is_encrypted else "plain"
    print(
        f"Created wallet {wallet.label} ({wallet.account_id}) with {wallet.algo_id} "
        f"[{storage_mode}] -> {args.output}"
    )
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    allocations = []
    for spec in args.allocation:
        wallet_path, amount = _parse_allocation(spec)
        allocations.append((load_wallet(wallet_path), amount))

    chain = PQAgileChain.bootstrap(difficulty=args.difficulty, wallet_allocations=allocations)
    chain.save(args.chain)
    print(
        f"Initialized chain at {args.chain} with {len(allocations)} genesis accounts and difficulty={args.difficulty}"
    )
    return 0


def cmd_transfer(args: argparse.Namespace) -> int:
    chain = PQAgileChain.load(args.chain)
    sender_wallet = _load_wallet_for_signing(
        args.wallet,
        password=args.wallet_password,
        password_env=args.wallet_password_env,
    )
    recipient_account_id = (
        load_wallet(args.to_wallet).account_id if args.to_wallet else args.to_account
    )
    tx = chain.queue_transfer(
        sender_wallet=sender_wallet,
        recipient_account_id=recipient_account_id,
        amount=args.amount,
    )
    chain.save(args.chain)
    print(
        f"Queued transfer nonce={tx.nonce} from {tx.sender_account_id} to {tx.recipient_account_id} amount={tx.amount}"
    )
    return 0


def cmd_rotate_key(args: argparse.Namespace) -> int:
    chain = PQAgileChain.load(args.chain)
    current_wallet = _load_wallet_for_signing(
        args.wallet,
        password=args.wallet_password,
        password_env=args.wallet_password_env,
    )
    new_floor = (
        args.new_security_floor
        if args.new_security_floor is not None
        else current_wallet.security_floor
    )
    new_wallet_password = resolve_wallet_password(
        password=args.new_wallet_password,
        password_env=args.new_wallet_password_env,
    )
    if new_wallet_password is None:
        new_wallet_password = resolve_wallet_password(
            password=args.wallet_password,
            password_env=args.wallet_password_env,
            default_env=DEFAULT_WALLET_PASSWORD_ENV,
        )
    new_wallet = create_wallet(
        algo_id=args.new_algo,
        label=args.new_label or f"{current_wallet.label}-rotated",
        security_floor=new_floor,
        account_id=current_wallet.account_id,
        password=new_wallet_password,
    )

    tx = chain.queue_rotation(current_wallet=current_wallet, new_wallet=new_wallet)
    chain.save(args.chain)
    save_wallet(new_wallet, args.new_wallet_out)
    print(
        f"Queued rotation nonce={tx.nonce} for {tx.account_id}: {tx.old_algo_id} -> {tx.new_algo_id}"
    )
    print(f"New wallet written to {args.new_wallet_out}")
    return 0


def cmd_mine(args: argparse.Namespace) -> int:
    chain = PQAgileChain.load(args.chain)
    block = chain.mine_pending()
    chain.save(args.chain)
    print(
        f"Mined block #{block.index} with {len(block.transactions)} tx(s), hash={block.block_hash}"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    chain = PQAgileChain.load(args.chain)
    state = chain.validate()
    print(
        f"Chain is valid with {len(chain.blocks)} block(s), {len(chain.mempool)} pending tx(s), {len(state)} account(s)"
    )
    for account_id in sorted(state):
        account = state[account_id]
        print(
            f"- {account.label} ({account.account_id}) balance={account.balance} nonce={account.nonce} "
            f"algo={account.algo_id} floor={account.security_floor}"
        )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir)
    wallets_dir = workdir / "wallets"
    wallets_dir.mkdir(parents=True, exist_ok=True)
    wallet_password = resolve_wallet_password(
        password=args.wallet_password,
        password_env=args.wallet_password_env,
        default_env=DEFAULT_WALLET_PASSWORD_ENV,
    )

    alice = create_wallet(
        algo_id="ml-dsa-65",
        label="alice",
        security_floor=3,
        password=wallet_password,
    )
    bob = create_wallet(
        algo_id="ml-dsa-65",
        label="bob",
        security_floor=3,
        password=wallet_password,
    )
    alice_wallet_path = save_wallet(alice, wallets_dir / "alice.wallet.json")
    bob_wallet_path = save_wallet(bob, wallets_dir / "bob.wallet.json")

    chain = PQAgileChain.bootstrap(
        difficulty=args.difficulty,
        wallet_allocations=[(alice, 120), (bob, 25)],
    )
    chain_path = chain.save(workdir / "chain.json")

    transfer1 = chain.queue_transfer(
        sender_wallet=alice, recipient_account_id=bob.account_id, amount=15
    )
    block1 = chain.mine_pending()

    alice_rotated = create_wallet(
        algo_id="sphincs-shake-256s-simple",
        label="alice-rotated",
        security_floor=5,
        account_id=alice.account_id,
        password=wallet_password,
    )
    alice_rotated_path = save_wallet(alice_rotated, wallets_dir / "alice-rotated.wallet.json")
    rotate_tx = chain.queue_rotation(current_wallet=alice, new_wallet=alice_rotated)
    block2 = chain.mine_pending()

    transfer2 = chain.queue_transfer(
        sender_wallet=alice_rotated, recipient_account_id=bob.account_id, amount=9
    )
    block3 = chain.mine_pending()

    old_wallet_error = ""
    try:
        chain.queue_transfer(sender_wallet=alice, recipient_account_id=bob.account_id, amount=1)
    except ChainValidationError as exc:
        old_wallet_error = str(exc)
    else:
        raise ChainValidationError("Old wallet unexpectedly remained valid after rotation")

    downgrade_wallet = create_wallet(
        algo_id="ml-dsa-65",
        label="alice-downgrade-attempt",
        security_floor=3,
        account_id=alice.account_id,
        password=wallet_password,
    )
    downgrade_error = ""
    try:
        chain.queue_rotation(current_wallet=alice_rotated, new_wallet=downgrade_wallet)
    except ChainValidationError as exc:
        downgrade_error = str(exc)
    else:
        raise ChainValidationError("security_floor downgrade unexpectedly succeeded")

    chain.save(chain_path)
    final_state = chain.validate()

    summary = {
        "chain_path": str(chain_path),
        "wallets": {
            "alice": str(alice_wallet_path),
            "alice_rotated": str(alice_rotated_path),
            "bob": str(bob_wallet_path),
        },
        "blocks": [
            {"index": block.index, "hash": block.block_hash, "tx_count": len(block.transactions)}
            for block in chain.blocks
        ],
        "transfer_nonces": [transfer1.nonce, transfer2.nonce],
        "rotation_nonce": rotate_tx.nonce,
        "expected_failures": {
            "old_wallet_reuse": old_wallet_error,
            "security_floor_downgrade": downgrade_error,
        },
        "final_balances": {
            account.label: account.balance
            for account in sorted(final_state.values(), key=lambda item: item.label)
        },
    }
    summary_path = workdir / "demo-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Demo completed successfully in {workdir}")
    print(f"- Chain: {chain_path}")
    print(f"- Summary: {summary_path}")
    print(f"- Old wallet rejection: {old_wallet_error}")
    print(f"- Downgrade rejection: {downgrade_error}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "create-wallet": cmd_create_wallet,
        "init": cmd_init,
        "transfer": cmd_transfer,
        "rotate-key": cmd_rotate_key,
        "mine": cmd_mine,
        "validate": cmd_validate,
        "demo": cmd_demo,
    }

    try:
        handler = commands.get(args.command)
        if handler is None:
            parser.error(f"Unknown command: {args.command}")
            return 2
        return handler(args)
    except (ChainValidationError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
