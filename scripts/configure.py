#!/usr/bin/env python3
"""
configure.py

Configuration script for llm-wiki skill.

Behavior:
1. Reads config.json in the same directory.
2. If "wiki_dir" is empty or not set, the default wiki directory is the
   `.wiki` folder under the current project workspace (where the agent is running).
3. If "wiki_dir" is set to a path, that path is used as the wiki directory.
4. Updates RULES.md to reflect the configured wiki directory so that all
   documentation references are consistent.

This script is intended to be run automatically when the skill is initialized
(via the /wiki init or /init slash command).
"""

import json
import os
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.resolve()
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_PATH = Path(os.getcwd()).resolve() / "config.json"
RULES_PATH = Path(os.getcwd()).resolve() / "RULES.md"

DEFAULT_WIKI_DIR_PLACEHOLDER = "{{DEFAULT_WIKI_DIR}}"


def get_default_wiki_dir() -> str:
    """
    Return the default wiki directory.
    When config is empty, default to `.wiki` under the current working directory
    (the project workspace).
    """
    return str(Path(os.getcwd()).resolve() / ".wiki")


def load_config() -> dict:
    """Load config.json, returning defaults if missing or malformed."""
    if not CONFIG_PATH.exists():
        return {"wiki_dir": ""}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"wiki_dir": ""}


def resolve_wiki_dir(config: dict) -> str:
    """Resolve the effective wiki directory from config."""
    wiki_dir = config.get("wiki_dir", "").strip()
    if not wiki_dir:
        return get_default_wiki_dir()
    return str(Path(wiki_dir).expanduser().resolve())


def update_rules_md(wiki_dir: str) -> None:
    """Update RULES.md so that the default wiki directory is documented."""
    if not RULES_PATH.exists():
        print(f"Warning: {RULES_PATH} not found, skipping update.")
        return

    with RULES_PATH.open("r", encoding="utf-8") as f:
        content = f.read()

    # Pattern to match the auto-managed block in RULES.md
    start_marker = "<!-- CONFIGURE_START -->"
    end_marker = "<!-- CONFIGURE_END -->"

    config_block = f"""{start_marker}
> **Auto-configured wiki directory:** `{wiki_dir}`
>
> This block is managed by `configure.py`. Do not edit manually.
{end_marker}"""

    if start_marker in content and end_marker in content:
        pattern = re.compile(
            re.escape(start_marker) + ".*?" + re.escape(end_marker),
            re.DOTALL,
        )
        new_content = pattern.sub(lambda m: config_block, content)
    else:
        # Insert after the first heading if markers don't exist yet
        new_content = content + "\n\n" + config_block + "\n"

    with RULES_PATH.open("w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated {RULES_PATH} with wiki_dir: {wiki_dir}")


def main() -> int:
    config = load_config()
    wiki_dir = resolve_wiki_dir(config)

    print(f"llm-wiki configured wiki directory: {wiki_dir}")

    # Ensure the directory exists
    Path(wiki_dir).mkdir(parents=True, exist_ok=True)

    update_rules_md(wiki_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
