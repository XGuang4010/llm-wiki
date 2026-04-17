#!/usr/bin/env python3
"""
wiki_stats.py

Outputs a quick health overview of the wiki as structured JSON.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def extract_wiki_links(text: str) -> List[str]:
    """Extract all [[...]] wiki link references from text."""
    links = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        raw = match.group(1).strip()
        stem = raw.split("|")[0].strip()
        if stem:
            links.append(stem)
    return links


def parse_log_operations(log_path: Path, limit: int = 5) -> List[dict]:
    """Parse wiki/log.md and return the last N operations (lines starting with '## [' )."""
    if not log_path.exists():
        return []
    try:
        text = log_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    operations = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## ["):
            m = re.match(r"##\s*\[([^\]]+)\]\s*(.*)", line)
            if m:
                date_str = m.group(1).strip()
                rest = m.group(2).strip()
                # Try to infer a type from the rest
                op_type = "other"
                lowered = rest.lower()
                if "ingest" in lowered:
                    op_type = "ingest"
                elif "commit" in lowered:
                    op_type = "commit"
                elif "sync" in lowered:
                    op_type = "sync"
                elif "lint" in lowered:
                    op_type = "lint"
                operations.append({"date": date_str, "type": op_type, "summary": rest})
    return operations[-limit:]


def find_latest_modification(wiki_dir: Path) -> Optional[dict]:
    """Find the most recently modified .md file under wiki/."""
    target = wiki_dir / "wiki"
    if not target.exists():
        return None
    latest: Optional[Path] = None
    latest_mtime = 0.0
    for p in target.rglob("*.md"):
        if not p.is_file():
            continue
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest = p
    if latest is None:
        return None
    mtime_dt = datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
    return {
        "file": latest.relative_to(wiki_dir).as_posix(),
        "mtime": mtime_dt.isoformat(),
    }


def run_stats(wiki_root: Path) -> dict:
    wiki_sub = wiki_root / "wiki"
    pages: Dict[str, int] = {
        "concepts": 0,
        "entities": 0,
        "sources": 0,
        "queries": 0,
        "comparisons": 0,
        "total": 0,
    }
    total_links = 0

    if wiki_sub.exists():
        for p in wiki_sub.rglob("*.md"):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(wiki_sub).parts
            if rel_parts:
                first_dir = rel_parts[0].lower()
                if first_dir in pages:
                    pages[first_dir] += 1
            pages["total"] += 1
            try:
                text = p.read_text(encoding="utf-8")
                total_links += len(extract_wiki_links(text))
            except UnicodeDecodeError:
                continue

    log_path = wiki_sub / "log.md"
    recent_activity = parse_log_operations(log_path, limit=5)
    latest_modification = find_latest_modification(wiki_root)

    now = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": now,
        "pages": pages,
        "links": {"total_wiki_links": total_links},
        "recent_activity": recent_activity,
        "latest_modification": latest_modification or {"file": None, "mtime": None},
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Output a quick health overview of the llm-wiki."
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=Path("."),
        help="Root of the wiki project (default: current directory)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to write the JSON report (default: print to stdout)",
    )
    args = parser.parse_args()

    wiki_root: Path = args.wiki_root.resolve()
    report = run_stats(wiki_root)
    report_json = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"Report written to {args.output}")
    else:
        print(report_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
