#!/usr/bin/env python3
"""
configure.py

Configuration script for llm-wiki skill.

Behavior:
1. Reads config.json from the skill directory first, then falls back to
   a project-level `.wiki/config.json` in the current working directory.
2. If "wiki_dir" is empty or not set, the default wiki directory is the
   `.wiki` folder under the current project workspace (where the agent is running).
3. If "wiki_dir" is set to a path, that path is used as the wiki directory.
4. Initializes the full llm-wiki directory structure under the resolved wiki_dir.
5. Updates RULES.md in the skill directory to reflect the configured wiki directory.

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
SKILL_CONFIG_PATH = SKILL_DIR / "config.json"
RULES_PATH = SKILL_DIR / "RULES.md"

DEFAULT_CONFIG = {"wiki_dir": ""}


def get_default_wiki_dir() -> str:
    """
    Return the default wiki directory.
    When config is empty, default to `.wiki` under the current working directory
    (the project workspace).
    """
    return str(Path(os.getcwd()).resolve() / ".wiki")


def load_json_config(path: Path) -> dict:
    """Load a JSON config file, returning an empty dict if missing or malformed."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_config() -> dict:
    """
    Load configuration with the following precedence:
    1. Skill-level config.json (SKILL_DIR / config.json)
    2. Project-level override: .wiki/config.json under cwd
    3. Hard-coded defaults
    """
    config = dict(DEFAULT_CONFIG)
    skill_config = load_json_config(SKILL_CONFIG_PATH)
    if skill_config:
        config.update(skill_config)

    project_config_path = Path(os.getcwd()).resolve() / ".wiki" / "config.json"
    project_config = load_json_config(project_config_path)
    if project_config:
        config.update(project_config)

    return config


def resolve_wiki_dir(config: dict) -> str:
    """Resolve the effective wiki directory from config."""
    wiki_dir = config.get("wiki_dir", "").strip()
    if not wiki_dir:
        return get_default_wiki_dir()
    return str(Path(wiki_dir).expanduser().resolve())


def init_directory_structure(wiki_dir: Path) -> None:
    """Create the full llm-wiki directory structure and default files."""
    subdirs = [
        "raw/articles",
        "wiki/concepts",
        "wiki/entities",
        "wiki/sources",
        "wiki/queries",
        "wiki/comparisons",
    ]
    for subdir in subdirs:
        (wiki_dir / subdir).mkdir(parents=True, exist_ok=True)

    index_path = wiki_dir / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Wiki Index\n\n"
            "This is the auto-generated index for your llm-wiki.\n\n"
            "- [Concepts](concepts/)\n"
            "- [Entities](entities/)\n"
            "- [Sources](sources/)\n"
            "- [Queries](queries/)\n"
            "- [Comparisons](comparisons/)\n",
            encoding="utf-8",
        )

    log_path = wiki_dir / "wiki" / "log.md"
    if not log_path.exists():
        log_path.write_text(
            "# Wiki Log\n\nTrack changes, updates, and decisions here.\n",
            encoding="utf-8",
        )

    project_config_path = Path(os.getcwd()).resolve() / ".wiki" / "config.json"
    if not project_config_path.exists():
        project_config_path.parent.mkdir(parents=True, exist_ok=True)
        with project_config_path.open("w", encoding="utf-8") as f:
            json.dump({"auto_commit": False}, f, indent=2)
            f.write("\n")


def update_rules_md(wiki_dir: str) -> None:
    """Update RULES.md so that the default wiki directory is documented."""
    if not RULES_PATH.exists():
        print(f"Warning: {RULES_PATH} not found, skipping update.")
        return

    with RULES_PATH.open("r", encoding="utf-8") as f:
        content = f.read()

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
        new_content = content + "\n\n" + config_block + "\n"

    with RULES_PATH.open("w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated {RULES_PATH} with wiki_dir: {wiki_dir}")


def main() -> int:
    config = load_config()
    wiki_dir = resolve_wiki_dir(config)

    print(f"llm-wiki configured wiki directory: {wiki_dir}")

    wiki_dir_path = Path(wiki_dir)
    init_directory_structure(wiki_dir_path)

    update_rules_md(wiki_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
