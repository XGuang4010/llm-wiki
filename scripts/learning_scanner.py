#!/usr/bin/env python3
"""
learning_scanner.py

Scans the filesystem for .learning directories, maintains a persistent
JSON index of file MD5 hashes, and reports new/changed files for ingestion
into the llm-wiki knowledge base.

Designed to work across agent products:
- Claude Code
- Codex (OpenAI)
- Trae
- Kimi Code
- CodeBuddy
- and any tool that stores learning data in .learning/
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


DEFAULT_IGNORE_PATTERNS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".DS_Store",
    "Thumbs.db",
}


def compute_md5(file_path: Path) -> str:
    """Compute MD5 hex digest for a file."""
    h = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def should_ignore(path: Path, ignore_patterns: Set[str]) -> bool:
    """Check if any component of the path matches an ignore pattern."""
    for part in path.parts:
        if part in ignore_patterns:
            return True
    return False


def find_learning_dirs(root: Path, max_depth: Optional[int] = None) -> List[Path]:
    """
    Find all directories named '.learning' under root.
    If max_depth is provided, stop descending after that many levels.
    """
    results: List[Path] = []
    root_resolved = root.resolve()

    for dirpath, dirnames, _ in os.walk(root_resolved):
        current = Path(dirpath)
        rel_parts = current.relative_to(root_resolved).parts
        if max_depth is not None and len(rel_parts) >= max_depth:
            dirnames.clear()
            continue

        if ".learning" in dirnames:
            results.append(current / ".learning")
            # Do not descend into .learning itself
            dirnames.remove(".learning")

    return results


def scan_learning_dir(learning_dir: Path, ignore_patterns: Set[str]) -> Dict[str, str]:
    """
    Scan a single .learning directory and return a dict mapping
    relative paths (to learning_dir) -> md5 hex digest.
    """
    files_map: Dict[str, str] = {}
    for file_path in learning_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(learning_dir).as_posix()
        if should_ignore(file_path, ignore_patterns):
            continue
        try:
            files_map[rel] = compute_md5(file_path)
        except OSError:
            continue
    return files_map


def load_index(index_path: Path) -> dict:
    """Load the JSON index file, returning an empty structure if missing."""
    if not index_path.exists():
        return {
            "version": 1,
            "created": datetime.now(timezone.utc).isoformat(),
            "last_scan": None,
            "directories": {},
        }
    with index_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index_path: Path, data: dict) -> None:
    """Save the JSON index file atomically."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(index_path)


def diff_against_index(
    scan_results: Dict[str, Dict[str, str]],
    index_data: dict,
) -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Compare scan results against the stored index.

    Returns:
        - added: files new since last scan
        - changed: files whose MD5 changed
        - removed: files that no longer exist
    """
    added: List[dict] = []
    changed: List[dict] = []
    removed: List[dict] = []

    stored_dirs = index_data.get("directories", {})

    for dir_path_str, current_files in scan_results.items():
        stored_files = stored_dirs.get(dir_path_str, {})
        stored_set = set(stored_files.keys())
        current_set = set(current_files.keys())

        for rel_path in current_set - stored_set:
            added.append(
                {
                    "learning_dir": dir_path_str,
                    "relative_path": rel_path,
                    "md5": current_files[rel_path],
                }
            )

        for rel_path in current_set & stored_set:
            if stored_files[rel_path] != current_files[rel_path]:
                changed.append(
                    {
                        "learning_dir": dir_path_str,
                        "relative_path": rel_path,
                        "old_md5": stored_files[rel_path],
                        "new_md5": current_files[rel_path],
                    }
                )

        for rel_path in stored_set - current_set:
            removed.append(
                {
                    "learning_dir": dir_path_str,
                    "relative_path": rel_path,
                    "md5": stored_files[rel_path],
                }
            )

    # Directories that disappeared entirely
    for dir_path_str in set(stored_dirs.keys()) - set(scan_results.keys()):
        for rel_path, md5_val in stored_dirs[dir_path_str].items():
            removed.append(
                {
                    "learning_dir": dir_path_str,
                    "relative_path": rel_path,
                    "md5": md5_val,
                }
            )

    return added, changed, removed


def build_report(
    added: List[dict],
    changed: List[dict],
    removed: List[dict],
    scan_results: Dict[str, Dict[str, str]],
) -> dict:
    """Build the JSON report structure."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "summary": {
            "total_learning_dirs": len(scan_results),
            "total_files_scanned": sum(len(v) for v in scan_results.values()),
            "added": len(added),
            "changed": len(changed),
            "removed": len(removed),
        },
        "added": added,
        "changed": changed,
        "removed": removed,
    }


def make_safe_slug(learning_dir: Path, rel_path: str, scan_root: Path) -> str:
    """
    Generate a unique, filesystem-safe slug from:
    - the parent directory name of .learning (relative to scan_root)
    - the relative path inside .learning
    Joined by '__' with path separators replaced by '_'.
    """
    learning_parent = learning_dir.parent.resolve()
    try:
        parent_rel = learning_parent.relative_to(scan_root.resolve())
    except ValueError:
        # scan_root is not an ancestor (shouldn't happen with normal usage)
        parent_rel = learning_parent

    parent_part = parent_rel.as_posix()
    # Drop leading ./ if present
    if parent_part.startswith("./"):
        parent_part = parent_part[2:]

    # Combine parent and inner relative path, strip original extension
    stem = Path(rel_path).stem
    combined = f"{parent_part}__{stem}"

    # Replace any path-like or unsafe chars with '_'
    safe = re.sub(r"[^\w\-]", "_", combined)
    # Avoid double underscores
    safe = re.sub(r"_+", "_", safe)
    safe = safe.strip("_")
    return safe


def stage_file(
    item: dict,
    scan_root: Path,
    raw_dir: Path,
    today: str,
) -> dict:
    """
    Copy a single changed/new file into raw/articles/ with frontmatter.
    Returns the manifest entry.
    """
    learning_dir = Path(item["learning_dir"])
    rel_path = item["relative_path"]
    original_file = learning_dir / rel_path

    safe_slug = make_safe_slug(learning_dir, rel_path, scan_root)
    raw_filename = f"{today}-{safe_slug}.md"
    raw_path = raw_dir / raw_filename

    # If collision exists, append a short hash suffix
    counter = 1
    original_raw_path = raw_path
    while raw_path.exists():
        short_hash = compute_md5(original_file)[:6]
        raw_path = raw_dir / f"{today}-{safe_slug}_{short_hash}_{counter}.md"
        counter += 1
        # Safety break
        if counter > 100:
            raw_path = original_raw_path
            break

    frontmatter = f"""---
title: {Path(rel_path).stem}
type: raw-source
source: learning_file
tags: [learning, self-improvement]
created: {today}
summary: Auto-staged from .learning directory
original_path: {original_file.resolve().as_posix()}
---

"""
    raw_dir.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as out_f:
        out_f.write(frontmatter)
        try:
            with original_file.open("r", encoding="utf-8") as in_f:
                out_f.write(in_f.read())
        except UnicodeDecodeError:
            # Fallback: treat as binary, skip content body
            out_f.write("\n\n<!-- Binary file content omitted -->\n")

    return {
        "original": str(original_file.resolve()),
        "learning_dir": item["learning_dir"],
        "relative_path": rel_path,
        "raw_path": raw_path.relative_to(raw_dir.parent).as_posix(),
        "status": item.get("status", "added"),
        "md5": item["md5"],
    }


def stage_files(
    added: List[dict],
    changed: List[dict],
    scan_root: Path,
    wiki_root: Path,
) -> List[dict]:
    """Stage all added/changed files into raw/articles/."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_dir = wiki_root / "raw" / "articles"

    manifest_entries: List[dict] = []

    for item in added:
        item["status"] = "added"
        manifest_entries.append(stage_file(item, scan_root, raw_dir, today))

    for item in changed:
        item["status"] = "changed"
        manifest_entries.append(stage_file(item, scan_root, raw_dir, today))

    return manifest_entries


def save_manifest(manifest_path: Path, entries: List[dict]) -> None:
    """Save the ingest manifest."""
    manifest = {
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "sources": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    tmp.replace(manifest_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan .learning directories and report new/changed files for llm-wiki ingestion."
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=Path("."),
        help="Root of the wiki project (default: current directory)",
    )
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=None,
        help="Root directory to scan for .learning folders (default: same as --wiki-root)",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=None,
        help="Path to the persistent JSON index (default: <wiki-root>/.wiki/learning_index.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to write the JSON report (default: print to stdout)",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        default=True,
        help="Update the persistent index after scanning (default: True)",
    )
    parser.add_argument(
        "--no-update-index",
        action="store_false",
        dest="update_index",
        help="Do not update the persistent index after scanning",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum depth to search for .learning directories",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Additional directory/file names to ignore (can be used multiple times)",
    )
    parser.add_argument(
        "--auto-stage",
        action="store_true",
        default=False,
        help="Automatically copy changed/new files into raw/articles/ with frontmatter",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to the ingest manifest (default: <wiki-root>/.wiki/ingest_manifest.json)",
    )

    args = parser.parse_args()

    wiki_root: Path = args.wiki_root.resolve()
    scan_root: Path = (args.scan_root or wiki_root).resolve()
    index_path: Path = args.index or wiki_root / ".wiki" / "learning_index.json"
    manifest_path: Path = args.manifest or wiki_root / ".wiki" / "ingest_manifest.json"
    ignore_patterns = DEFAULT_IGNORE_PATTERNS | set(args.ignore)

    # 1. Find all .learning directories
    learning_dirs = find_learning_dirs(scan_root, max_depth=args.max_depth)

    # 2. Scan each directory
    scan_results: Dict[str, Dict[str, str]] = {}
    for ld in learning_dirs:
        scan_results[ld.as_posix()] = scan_learning_dir(ld, ignore_patterns)

    # 3. Load existing index and diff
    index_data = load_index(index_path)
    added, changed, removed = diff_against_index(scan_results, index_data)

    # 4. Auto-stage if requested
    manifest_entries: List[dict] = []
    if args.auto_stage and (added or changed):
        manifest_entries = stage_files(added, changed, scan_root, wiki_root)
        save_manifest(manifest_path, manifest_entries)
        print(f"Staged {len(manifest_entries)} file(s) to raw/articles/")
        print(f"Manifest saved: {manifest_path}")

    # 5. Build report
    report = build_report(added, changed, removed, scan_results)

    # 6. Output
    report_json = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"Report written to {args.output}")
    else:
        print(report_json)

    # 7. Update index if requested
    if args.update_index:
        index_data["last_scan"] = datetime.now(timezone.utc).isoformat()
        index_data["directories"] = scan_results
        save_index(index_path, index_data)
        print(f"Index updated: {index_path}")

    # Return non-zero if there are changes, so callers (e.g., cron scripts) can react
    return 0 if not (added or changed) else 1


if __name__ == "__main__":
    sys.exit(main())
