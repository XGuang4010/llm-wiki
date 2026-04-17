#!/usr/bin/env python3
"""
wiki_commit.py

Auto-commits wiki changes if auto_commit is enabled in config.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_config(config_path: Path) -> dict:
    """Load .wiki/config.json if it exists."""
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_git_repo(path: Path) -> bool:
    """Check if the given path is inside a git repository."""
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_has_changes(path: Path) -> bool:
    """Check if there are any staged or unstaged changes in the repo."""
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def git_add_all(path: Path) -> bool:
    """Run git add -A in the repo."""
    result = subprocess.run(
        ["git", "-C", str(path), "add", "-A"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def git_commit(path: Path, message: str) -> bool:
    """Run git commit in the repo."""
    result = subprocess.run(
        ["git", "-C", str(path), "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-commit wiki changes if enabled in config."
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=Path("."),
        help="Root of the wiki project (default: current directory)",
    )
    parser.add_argument(
        "--message",
        "-m",
        type=str,
        default="Auto-commit wiki changes",
        help="Commit message",
    )
    args = parser.parse_args()

    wiki_root: Path = args.wiki_root.resolve()
    config_path = wiki_root / ".wiki" / "config.json"
    config = load_config(config_path)

    if not config.get("auto_commit", False):
        print("Auto-commit disabled.")
        return 0

    if not is_git_repo(wiki_root):
        print("Error: wiki root is not inside a git repository.", file=sys.stderr)
        return 1

    if not git_has_changes(wiki_root):
        print("Nothing to commit.")
        return 0

    if not git_add_all(wiki_root):
        print("Error: git add failed.", file=sys.stderr)
        return 1

    if not git_commit(wiki_root, args.message):
        print("Error: git commit failed.", file=sys.stderr)
        return 1

    print(f"Committed with message: {args.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
