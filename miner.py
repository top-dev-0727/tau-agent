"""
miner.py — Bittensor SN66 miner loop.

The miner's job is simple:
  1. Connect to the Bittensor chain on netuid 66.
  2. Publish (or refresh) an on-chain commitment that points to a public
     GitHub repo + commit SHA containing the miner's coding-agent code.
  3. Periodically re-check the current HEAD of the local agent repo and
     update the commitment when the SHA changes (i.e. after the miner
     pushes an improvement).

Commitment format expected by the validator:
    owner/repo@<full-or-short-sha>
  or the long form:
    https://github.com/owner/repo/commit/<sha>

Usage:
    python -m miner \
        --wallet-name  my_wallet \
        --wallet-hotkey my_hotkey \
        --repo         owner/repo \
        --agent-sha    abc1234       # optional: default is HEAD of --agent-dir

Environment variables (loaded from .env automatically):
    BT_WALLET_PATH      override the default wallet directory
    GITHUB_TOKEN        optional, for verifying the commit is public
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Dotenv loading (same approach as the rest of the project)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with env_path.open() as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

log = logging.getLogger("swe-eval.miner")

# Re-use Subnet 66 netuid constant from config to stay consistent.
_DEFAULT_NETUID = 66
_DEFAULT_POLL_INTERVAL = 300  # seconds between SHA checks


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_head_sha(repo_dir: Path) -> str | None:
    """Return the full SHA of HEAD in *repo_dir*, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as exc:
        log.debug("git rev-parse HEAD failed: %s", exc)
    return None


def _git_remote_url(repo_dir: Path) -> str | None:
    """Return the push URL of the 'origin' remote, or None."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as exc:
        log.debug("git remote get-url failed: %s", exc)
    return None


def _extract_repo_name_from_url(url: str) -> str | None:
    """Parse an 'owner/repo' slug from a GitHub remote URL."""
    # Handles https://github.com/owner/repo.git and git@github.com:owner/repo.git
    url = url.strip().rstrip("/").removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if url.startswith(prefix):
            slug = url[len(prefix):]
            parts = [p for p in slug.split("/") if p]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
    if url.startswith("git@github.com:"):
        slug = url[len("git@github.com:"):]
        parts = [p for p in slug.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return None


# ---------------------------------------------------------------------------
# Bittensor helpers
# ---------------------------------------------------------------------------

def _open_subtensor(args: argparse.Namespace):
    """Return a connected bt.Subtensor instance."""
    import bittensor as bt  # noqa: PLC0415

    kwargs: dict = {}
    if args.network:
        kwargs["network"] = args.network
    if args.subtensor_endpoint:
        kwargs["chain_endpoint"] = args.subtensor_endpoint
    return bt.Subtensor(**kwargs)


def _load_wallet(args: argparse.Namespace):
    """Return a bt.Wallet loaded from CLI args."""
    import bittensor as bt  # noqa: PLC0415

    kwargs: dict = {
        "name": args.wallet_name,
        "hotkey": args.wallet_hotkey,
    }
    if args.wallet_path:
        kwargs["path"] = args.wallet_path
    elif os.environ.get("BT_WALLET_PATH"):
        kwargs["path"] = os.environ["BT_WALLET_PATH"]
    return bt.Wallet(**kwargs)


# ---------------------------------------------------------------------------
# Commitment helpers
# ---------------------------------------------------------------------------

def _build_commitment(repo: str, sha: str) -> str:
    """Build the commitment string in the format the validator expects."""
    return f"{repo}@{sha}"


def _get_current_on_chain_commitment(subtensor, wallet, netuid: int) -> str | None:
    """Return the miner's currently committed string, or None."""
    try:
        commitments = subtensor.commitments.get_all_commitments(netuid)
        hotkey = wallet.hotkey.ss58_address
        for hk, commitment in commitments.items():
            if str(hk) == hotkey:
                return str(commitment)
    except Exception as exc:
        log.warning("Could not fetch current commitment: %s", exc)
    return None


def _submit_commitment(subtensor, wallet, netuid: int, commitment: str) -> bool:
    """Publish *commitment* on-chain. Returns True on success."""
    try:
        subtensor.commitments.set_commitment(
            wallet=wallet,
            netuid=netuid,
            data=commitment,
        )
        log.info("Commitment published: %s", commitment)
        return True
    except Exception as exc:
        log.error("Failed to submit commitment: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main miner loop
# ---------------------------------------------------------------------------

def miner_loop(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Resolve repo slug --------------------------------------------------
    repo_slug: str | None = args.repo

    agent_dir: Path | None = None
    if args.agent_dir:
        agent_dir = Path(args.agent_dir).resolve()
        if not agent_dir.exists():
            log.error("--agent-dir %s does not exist", agent_dir)
            sys.exit(1)

        if repo_slug is None:
            remote = _git_remote_url(agent_dir)
            if remote:
                repo_slug = _extract_repo_name_from_url(remote)
            if repo_slug is None:
                log.error(
                    "Could not determine GitHub repo from remote URL of %s. "
                    "Pass --repo owner/repo explicitly.",
                    agent_dir,
                )
                sys.exit(1)
        log.info("Agent directory: %s  →  repo: %s", agent_dir, repo_slug)

    if repo_slug is None:
        log.error("Must provide --repo owner/repo or --agent-dir pointing to a git repo.")
        sys.exit(1)

    log.info(
        "Miner starting. netuid=%d  wallet=%s/%s  repo=%s  poll_interval=%ds",
        args.netuid,
        args.wallet_name,
        args.wallet_hotkey,
        repo_slug,
        args.poll_interval,
    )

    last_submitted_sha: str | None = None

    while True:
        try:
            # Determine the current SHA to advertise --------------------
            if args.agent_sha:
                sha = args.agent_sha
            elif agent_dir:
                sha = _git_head_sha(agent_dir)
                if sha is None:
                    log.warning("Could not read HEAD from %s; will retry", agent_dir)
                    time.sleep(args.poll_interval)
                    continue
            else:
                log.error("No SHA source — provide --agent-sha or --agent-dir")
                sys.exit(1)

            commitment = _build_commitment(repo_slug, sha)

            # Skip if we already published this exact commitment ---------
            if sha == last_submitted_sha:
                log.debug("SHA unchanged (%s), no update needed", sha[:12])
                time.sleep(args.poll_interval)
                continue

            # Connect to chain and submit --------------------------------
            subtensor = _open_subtensor(args)
            wallet = _load_wallet(args)

            current = _get_current_on_chain_commitment(subtensor, wallet, args.netuid)
            if current == commitment:
                log.info("On-chain commitment already matches (%s), skipping tx", commitment)
                last_submitted_sha = sha
                subtensor.close()
                time.sleep(args.poll_interval)
                continue

            log.info(
                "Updating commitment: %s  →  %s",
                current or "<none>",
                commitment,
            )
            ok = _submit_commitment(subtensor, wallet, args.netuid, commitment)
            subtensor.close()

            if ok:
                last_submitted_sha = sha

        except KeyboardInterrupt:
            log.info("Miner stopped by user.")
            break
        except Exception as exc:
            log.exception("Unhandled error in miner loop: %s", exc)

        time.sleep(args.poll_interval)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SN66 miner: watches a local agent repo and keeps an on-chain "
            "commitment up-to-date so the validator can evaluate it."
        )
    )
    parser.add_argument("--wallet-name", required=True, help="Bittensor wallet coldkey name.")
    parser.add_argument("--wallet-hotkey", required=True, help="Bittensor wallet hotkey name.")
    parser.add_argument("--wallet-path", help="Override the default wallet directory.")
    parser.add_argument(
        "--netuid",
        type=int,
        default=_DEFAULT_NETUID,
        help=f"Subnet netuid (default: {_DEFAULT_NETUID}).",
    )
    parser.add_argument("--network", help="Bittensor network name or websocket endpoint.")
    parser.add_argument("--subtensor-endpoint", help="Websocket endpoint override.")
    parser.add_argument(
        "--repo",
        help=(
            "GitHub repo slug in 'owner/repo' format. "
            "Inferred from the git remote of --agent-dir if omitted."
        ),
    )
    parser.add_argument(
        "--agent-dir",
        default="./agent",
        help="Path to the local agent git repo (default: ./agent). "
             "The miner watches HEAD here and submits it when it changes.",
    )
    parser.add_argument(
        "--agent-sha",
        help=(
            "Fixed commit SHA to advertise. Useful for one-shot submissions. "
            "If provided, --agent-dir is only used to infer --repo."
        ),
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=_DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help=f"How often to check for a new HEAD SHA (default: {_DEFAULT_POLL_INTERVAL}s).",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    miner_loop(args)


if __name__ == "__main__":
    main()
