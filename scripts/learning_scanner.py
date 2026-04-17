#!/usr/bin/env python3
"""
learning_scanner.py

Scans the filesystem for .learning directories and .wiki directories,
maintains a persistent JSON index of file MD5 hashes, and reports
new/changed files for ingestion into the llm-wiki knowledge base.

Designed to work across agent products:
- Claude Code
- Codex (OpenAI)
- Trae
- Kimi Code
- CodeBuddy
- and any tool that stores learning data in .learning/ or .wiki/
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

WIKI_METADATA_FILES = {
    "learning_index.json",
    "ingest_manifest.json",
    "doc_index.json",
    "wiki_index.json",
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


def find_wiki_dirs(
    root: Path,
    max_depth: Optional[int] = None,
    exclude: Optional[Path] = None,
) -> List[Path]:
    """
    Find all directories named '.wiki' under root.
    If max_depth is provided, stop descending after that many levels.
    If exclude is provided, skip that exact path.
    """
    results: List[Path] = []
    root_resolved = root.resolve()
    exclude_resolved = exclude.resolve() if exclude else None

    for dirpath, dirnames, _ in os.walk(root_resolved):
        current = Path(dirpath)
        rel_parts = current.relative_to(root_resolved).parts
        if max_depth is not None and len(rel_parts) >= max_depth:
            dirnames.clear()
            continue

        if ".wiki" in dirnames:
            wiki_path = current / ".wiki"
            if exclude_resolved is None or wiki_path.resolve() != exclude_resolved:
                results.append(wiki_path)
            # Do not descend into .wiki itself
            dirnames.remove(".wiki")

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


def scan_wiki_dir(wiki_dir: Path, ignore_patterns: Set[str]) -> Dict[str, str]:
    """
    Scan a single .wiki directory and return a dict mapping
    relative paths (to wiki_dir) -> md5 hex digest.
    Only scans 'raw/' and 'wiki/' subdirectories.
    """
    files_map: Dict[str, str] = {}
    for subdir_name in ("raw", "wiki"):
        subdir = wiki_dir / subdir_name
        if not subdir.exists():
            continue
        for file_path in subdir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(wiki_dir).as_posix()
            if should_ignore(file_path, ignore_patterns):
                continue
            if file_path.name in WIKI_METADATA_FILES:
                continue
            try:
                files_map[rel] = compute_md5(file_path)
            except OSError:
                continue
    return files_map


def load_index(index_path: Path) -> dict:
    """
    Load the JSON index file, returning an empty structure if missing.
    Auto-migrates from old learning_index.json to doc_index.json.
    """
    # Migration: if doc_index.json doesn't exist but learning_index.json does
    old_path = index_path.with_name("learning_index.json")
    if not index_path.exists() and old_path.exists():
        try:
            with old_path.open("r", encoding="utf-8") as f:
                old_data = json.load(f)
            migrated = {
                "version": 2,
                "created": old_data.get(
                    "created", datetime.now(timezone.utc).isoformat()
                ),
                "last_scan": old_data.get("last_scan"),
                "learning_directories": old_data.get("directories", {}),
                "wiki_directories": {},
                "wiki_targets": {},
            }
            old_path.unlink()
            save_index(index_path, migrated)
            return migrated
        except (json.JSONDecodeError, OSError):
            pass

    if not index_path.exists():
        return {
            "version": 2,
            "created": datetime.now(timezone.utc).isoformat(),
            "last_scan": None,
            "learning_directories": {},
            "wiki_directories": {},
            "wiki_targets": {},
        }
    with index_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Ensure v2 fields exist even if file was manually edited
    data.setdefault("learning_directories", {})
    data.setdefault("wiki_directories", {})
    data.setdefault("wiki_targets", {})
    return data


def save_index(index_path: Path, data: dict) -> None:
    """Save the JSON index file atomically."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(index_path)


def diff_against_index(
    scan_results: Dict[str, Dict[str, str]],
    stored_dirs: Dict[str, Dict[str, str]],
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
                        "md5": current_files[rel_path],
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


def build_learning_report(
    added: List[dict],
    changed: List[dict],
    removed: List[dict],
    scan_results: Dict[str, Dict[str, str]],
) -> dict:
    """Build the JSON report structure for .learning scan."""
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


def stage_learning_files(
    added: List[dict],
    changed: List[dict],
    scan_root: Path,
    wiki_root: Path,
) -> List[dict]:
    """Stage all added/changed .learning files into raw/articles/."""
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


def resolve_wiki_target_path(
    wiki_root: Path,
    rel_path: str,
    occupied_targets: Dict[str, str],
    original_file: Path,
) -> Path:
    """
    Resolve the target path for a .wiki file, handling naming conflicts
    by appending _1, _2, etc.
    If the target is already occupied by the SAME source file (same inode/device
    on Windows: same resolved path), return that target path for overwrite.
    """
    target = wiki_root / rel_path
    target_str = str(target)

    # If this exact source file already owns this target, allow overwrite
    if target_str in occupied_targets:
        if occupied_targets[target_str] == str(original_file.resolve()):
            return target
    elif not target.exists():
        return target

    # Check if any occupied target is owned by this same source file
    for occupied_str, source_str in occupied_targets.items():
        if source_str == str(original_file.resolve()):
            occupied_path = Path(occupied_str)
            if occupied_path.exists():
                # Verify it's actually the same file (avoid stale mapping)
                try:
                    if occupied_path.stat().st_ino == original_file.stat().st_ino:
                        return occupied_path
                except (OSError, AttributeError):
                    pass

    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        candidate_str = str(candidate)
        if candidate_str not in occupied_targets and not candidate.exists():
            return candidate
        # If candidate is occupied by same source, allow overwrite
        if candidate_str in occupied_targets:
            if occupied_targets[candidate_str] == str(original_file.resolve()):
                return candidate
        counter += 1
        if counter > 9999:
            raise RuntimeError(f"Cannot resolve target path for {rel_path}")


def sync_wiki_files(
    items: List[dict],
    wiki_root: Path,
    occupied_targets: Dict[str, str],
) -> List[dict]:
    """
    Copy .wiki files directly into the total wiki directory structure.
    Returns a list of sync manifest entries.
    """
    manifest_entries: List[dict] = []

    for item in items:
        wiki_dir = Path(item["wiki_dir"])
        rel_path = item["relative_path"]
        original_file = wiki_dir / rel_path

        target_path = resolve_wiki_target_path(
            wiki_root, rel_path, occupied_targets, original_file
        )
        target_str = str(target_path)
        occupied_targets[target_str] = str(original_file.resolve())

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_file, target_path)

        manifest_entries.append(
            {
                "original": str(original_file.resolve()),
                "wiki_dir": str(wiki_dir),
                "relative_path": rel_path,
                "target_path": target_path.relative_to(wiki_root).as_posix(),
                "status": item.get("status", "synced"),
                "md5": item["md5"],
            }
        )

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


def build_combined_report(
    learning_added: List[dict],
    learning_changed: List[dict],
    learning_removed: List[dict],
    learning_results: Dict[str, Dict[str, str]],
    wiki_added: List[dict],
    wiki_changed: List[dict],
    wiki_removed: List[dict],
    wiki_results: Dict[str, Dict[str, str]],
    learning_manifest_count: int,
    wiki_manifest_count: int,
) -> dict:
    """Build combined report for both .learning and .wiki scans."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "summary": {
            "learning": {
                "dirs_found": len(learning_results),
                "files_scanned": sum(len(v) for v in learning_results.values()),
                "added": len(learning_added),
                "changed": len(learning_changed),
                "removed": len(learning_removed),
            },
            "wiki": {
                "dirs_found": len(wiki_results),
                "files_scanned": sum(len(v) for v in wiki_results.values()),
                "added": len(wiki_added),
                "changed": len(wiki_changed),
                "removed": len(wiki_removed),
            },
            "manifest": {
                "learning_staged": learning_manifest_count,
                "wiki_synced": wiki_manifest_count,
            },
        },
        "learning": {
            "added": learning_added,
            "changed": learning_changed,
            "removed": learning_removed,
        },
        "wiki": {
            "added": wiki_added,
            "changed": wiki_changed,
            "removed": wiki_removed,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan .learning and .wiki directories and report new/changed files for llm-wiki ingestion."
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
        help="Root directory to scan for .learning and .wiki folders (default: same as --wiki-root)",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=None,
        help="Path to the persistent JSON index (default: <wiki-root>/.wiki/doc_index.json)",
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
        help="Maximum depth to search for directories",
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
        help="Automatically copy changed/new files into the wiki",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to the ingest manifest (default: <wiki-root>/.wiki/ingest_manifest.json)",
    )
    parser.add_argument(
        "--wiki-full-sync",
        action="store_true",
        default=False,
        help="Force full synchronization of all .wiki files (ignore index)",
    )
    parser.add_argument(
        "--no-wiki-sync",
        action="store_true",
        default=False,
        help="Skip .wiki directory synchronization",
    )

    args = parser.parse_args()

    wiki_root: Path = args.wiki_root.resolve()
    scan_root: Path = (args.scan_root or wiki_root).resolve()
    index_path: Path = args.index or wiki_root / ".wiki" / "doc_index.json"
    manifest_path: Path = args.manifest or wiki_root / ".wiki" / "ingest_manifest.json"
    ignore_patterns = DEFAULT_IGNORE_PATTERNS | set(args.ignore)

    # 1. Find all .learning directories
    learning_dirs = find_learning_dirs(scan_root, max_depth=args.max_depth)

    # 2. Find all .wiki directories
    wiki_dirs = find_wiki_dirs(
        scan_root,
        max_depth=args.max_depth,
        exclude=wiki_root / ".wiki",
    )

    # 3. Scan each .learning directory
    learning_results: Dict[str, Dict[str, str]] = {}
    for ld in learning_dirs:
        learning_results[ld.as_posix()] = scan_learning_dir(ld, ignore_patterns)

    # 4. Scan each .wiki directory
    wiki_results: Dict[str, Dict[str, str]] = {}
    for wd in wiki_dirs:
        wiki_results[wd.as_posix()] = scan_wiki_dir(wd, ignore_patterns)

    # 5. Load existing index and diff
    index_data = load_index(index_path)
    learning_added, learning_changed, learning_removed = diff_against_index(
        learning_results, index_data.get("learning_directories", {})
    )
    wiki_added, wiki_changed, wiki_removed = diff_against_index(
        wiki_results, index_data.get("wiki_directories", {})
    )

    # 6. Auto-stage .learning if requested
    learning_manifest: List[dict] = []
    if args.auto_stage and (learning_added or learning_changed):
        learning_manifest = stage_learning_files(
            learning_added, learning_changed, scan_root, wiki_root
        )
        save_manifest(manifest_path, learning_manifest)
        print(f"Staged {len(learning_manifest)} .learning file(s) to raw/articles/")
        print(f"Manifest saved: {manifest_path}")

    # 7. Auto-sync .wiki if requested
    wiki_manifest: List[dict] = []
    if args.auto_stage and not args.no_wiki_sync:
        if args.wiki_full_sync:
            wiki_items = []
            for wiki_dir_str, files in wiki_results.items():
                for rel_path, md5 in files.items():
                    wiki_items.append(
                        {
                            "wiki_dir": wiki_dir_str,
                            "relative_path": rel_path,
                            "md5": md5,
                            "status": "synced",
                        }
                    )
            index_data["wiki_targets"] = {}
        else:
            wiki_items = []
            for item in wiki_added:
                wiki_items.append(
                    {
                        "wiki_dir": item["learning_dir"],
                        "relative_path": item["relative_path"],
                        "md5": item["md5"],
                        "status": "added",
                    }
                )
            for item in wiki_changed:
                wiki_items.append(
                    {
                        "wiki_dir": item["learning_dir"],
                        "relative_path": item["relative_path"],
                        "md5": item["md5"],
                        "status": "changed",
                    }
                )

        if wiki_items:
            occupied_targets: Dict[str, str] = {}
            if not args.wiki_full_sync:
                for wiki_dir_str, targets in index_data.get("wiki_targets", {}).items():
                    for rel_path, target_path in targets.items():
                        occupied_targets[str(wiki_root / target_path)] = wiki_dir_str

            wiki_manifest = sync_wiki_files(wiki_items, wiki_root, occupied_targets)

            wiki_targets = index_data.setdefault("wiki_targets", {})
            for entry in wiki_manifest:
                wd = entry["wiki_dir"]
                rel = entry["relative_path"]
                wiki_targets.setdefault(wd, {})[rel] = entry["target_path"]

            print(f"Synced {len(wiki_manifest)} .wiki file(s)")

    # 8. Build combined report
    report = build_combined_report(
        learning_added,
        learning_changed,
        learning_removed,
        learning_results,
        wiki_added,
        wiki_changed,
        wiki_removed,
        wiki_results,
        len(learning_manifest),
        len(wiki_manifest),
    )

    # 9. Output
    report_json = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"Report written to {args.output}")
    else:
        print(report_json)

    # 10. Update index if requested
    if args.update_index:
        index_data["last_scan"] = datetime.now(timezone.utc).isoformat()
        index_data["learning_directories"] = learning_results
        index_data["wiki_directories"] = wiki_results
        save_index(index_path, index_data)
        print(f"Index updated: {index_path}")

    # Return non-zero if there are changes
    has_changes = bool(learning_added or learning_changed or wiki_added or wiki_changed)
    return 0 if not has_changes else 1


if __name__ == "__main__":
    sys.exit(main())
