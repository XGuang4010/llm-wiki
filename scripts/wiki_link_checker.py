#!/usr/bin/env python3
"""
wiki_link_checker.py

Scans the wiki and checks for broken wiki-links, orphan pages, and missing backlinks.

Outputs a structured JSON report for the Agent to read and fix.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

EXCLUDED_STEMS = {"index", "log", "overview"}


def extract_wiki_links(text: str) -> Set[str]:
    """Extract all [[...]] wiki link stems from text."""
    links = set()
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        raw = match.group(1).strip()
        # Handle [[Concept|Display text]] -> Concept
        stem = raw.split("|")[0].strip()
        if stem:
            links.add(stem)
    return links


def find_wiki_pages(wiki_dir: Path) -> Dict[str, Path]:
    """Find all .md files under wiki/ and raw/articles/, return stem -> path mapping."""
    pages: Dict[str, Path] = {}
    
    # Scan wiki/ directory
    wiki_subdir = wiki_dir / "wiki"
    if wiki_subdir.exists():
        for p in wiki_subdir.rglob("*.md"):
            if p.is_file():
                pages[p.stem] = p
    
    # Scan raw/articles/ directory
    articles_subdir = wiki_dir / "raw" / "articles"
    if articles_subdir.exists():
        for p in articles_subdir.rglob("*.md"):
            if p.is_file() and p.stem not in pages:
                pages[p.stem] = p
    
    return pages


def get_line_number(text: str, position: int) -> int:
    """Get line number for a character position in text."""
    return text[:position].count("\n") + 1


def check_links(wiki_root: Path) -> dict:
    """Run the full link check and return a structured report."""
    pages = find_wiki_pages(wiki_root)
    
    broken_links: List[dict] = []
    all_links: Dict[str, Set[str]] = defaultdict(set)  # from_stem -> set(to_stems)
    link_locations: Dict[Tuple[str, str], List[int]] = defaultdict(list)  # (from, to) -> [line_numbers]
    page_backlinks: Dict[str, Set[str]] = defaultdict(set)  # to_stem -> set(from_stems)
    
    for stem, path in pages.items():
        if stem in EXCLUDED_STEMS:
            continue
            
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        
        links = extract_wiki_links(text)
        all_links[stem] = links
        
        for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
            raw = match.group(1).strip()
            to_stem = raw.split("|")[0].strip()
            if not to_stem:
                continue
            
            line = get_line_number(text, match.start())
            link_locations[(stem, to_stem)].append(line)
            page_backlinks[to_stem].add(stem)
            
            # Check if target exists
            if to_stem not in pages:
                broken_links.append({
                    "from": stem,
                    "from_path": str(path.relative_to(wiki_root)),
                    "to": to_stem,
                    "line": line,
                    "context": raw,
                })
    
    # Find orphan pages (no incoming links from other pages)
    orphan_pages: List[dict] = []
    for stem, path in pages.items():
        if stem in EXCLUDED_STEMS:
            continue
        if stem not in page_backlinks or len(page_backlinks[stem]) == 0:
            orphan_pages.append({
                "stem": stem,
                "path": str(path.relative_to(wiki_root)),
            })
    
    # Find missing backlinks (A links to B but B doesn't link back to A)
    missing_backlinks: List[dict] = []
    for from_stem, to_stems in all_links.items():
        if from_stem in EXCLUDED_STEMS:
            continue
        for to_stem in to_stems:
            if to_stem in EXCLUDED_STEMS:
                continue
            if to_stem not in all_links:
                continue  # Target page has no outgoing links at all
            if from_stem not in all_links[to_stem]:
                missing_backlinks.append({
                    "from": from_stem,
                    "to": to_stem,
                })
    
    # Find self-references (pages that don't link to anything)
    isolated_pages: List[dict] = []
    for stem, path in pages.items():
        if stem in EXCLUDED_STEMS:
            continue
        if stem not in all_links or len(all_links[stem]) == 0:
            isolated_pages.append({
                "stem": stem,
                "path": str(path.relative_to(wiki_root)),
            })
    
    # Build suggestions for broken links (fuzzy match)
    for bl in broken_links:
        target = bl["to"]
        # Find similar stems
        suggestions = []
        for existing_stem in pages.keys():
            if existing_stem == target:
                continue
            # Simple similarity: common substring or edit distance
            if target.lower() in existing_stem.lower() or existing_stem.lower() in target.lower():
                suggestions.append(existing_stem)
        if suggestions:
            bl["suggested_fixes"] = suggestions[:3]  # Top 3
    
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": now,
        "tool": "wiki_link_checker.py",
        "summary": {
            "total_pages": len(pages),
            "total_links": sum(len(links) for links in all_links.values()),
            "broken_links": len(broken_links),
            "orphan_pages": len(orphan_pages),
            "missing_backlinks": len(missing_backlinks),
            "isolated_pages": len(isolated_pages),
        },
        "broken_links": broken_links,
        "orphan_pages": orphan_pages,
        "missing_backlinks": missing_backlinks,
        "isolated_pages": isolated_pages,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check wiki-links for broken references, orphans, and missing backlinks."
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
    report = check_links(wiki_root)
    report_json = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"Link check report written to {args.output}")
        # Also print summary to stdout for visibility
        s = report["summary"]
        print(f"\nSummary: {s['total_pages']} pages, {s['total_links']} links")
        if s["broken_links"]:
            print(f"  🔴 Broken links: {s['broken_links']}")
        if s["orphan_pages"]:
            print(f"  🟡 Orphan pages: {s['orphan_pages']}")
        if s["missing_backlinks"]:
            print(f"  🟡 Missing backlinks: {s['missing_backlinks']}")
        if s["isolated_pages"]:
            print(f"  🟡 Isolated pages: {s['isolated_pages']}")
        if all(v == 0 for k, v in s.items() if k != "total_pages" and k != "total_links"):
            print("  🟢 All links healthy!")
    else:
        print(report_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
