#!/usr/bin/env python3
"""
wiki_lint.py

Scans the wiki and outputs a structured JSON report.
Does NOT make judgments or fixes — it only reports.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

EXCLUDED_ORPHANS = {"index", "log", "overview"}


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


def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Parse YAML-like frontmatter and return (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip().lower()] = value.strip()
    return fm, body


def find_md_files(wiki_dir: Path) -> List[Path]:
    """Find all .md files under wiki/."""
    target = wiki_dir / "wiki"
    if not target.exists():
        return []
    return sorted(p for p in target.rglob("*.md") if p.is_file())


def run_lint(wiki_root: Path) -> dict:
    md_files = find_md_files(wiki_root)
    all_links: Counter = Counter()
    all_stems: Dict[str, Path] = {}
    title_to_dates: Dict[str, List[str]] = {}
    empty_pages: List[str] = []
    orphan_candidates: Dict[str, Path] = {}
    file_contents: Dict[Path, str] = {}

    for p in md_files:
        rel = p.relative_to(wiki_root / "wiki").as_posix()
        stem = p.stem
        all_stems[stem] = p
        orphan_candidates[stem] = p
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        file_contents[p] = text
        fm, body = parse_frontmatter(text)
        links = extract_wiki_links(text)
        for link in links:
            all_links[link] += 1
        if "title" in fm:
            title_to_dates.setdefault(fm["title"], []).append(fm.get("created", ""))
        body_text = re.sub(r"\s+", "", body)
        if len(body_text) < 50:
            empty_pages.append(rel)

    # Orphan pages: stems never appearing as a link in any other page
    linked_stems: Set[str] = set()
    for p, text in file_contents.items():
        links = extract_wiki_links(text)
        for link in links:
            if link in orphan_candidates and link != p.stem:
                linked_stems.add(link)
    orphan_pages = sorted(
        orphan_candidates[s].relative_to(wiki_root / "wiki").as_posix()
        for s in set(orphan_candidates.keys()) - linked_stems - EXCLUDED_ORPHANS
    )

    # Missing concept pages: links mentioned >=3 times with no .md file in concepts/ or entities/
    concepts_dir = wiki_root / "wiki" / "concepts"
    entities_dir = wiki_root / "wiki" / "entities"
    missing_concepts = []
    for term, count in all_links.most_common():
        if count < 3:
            continue
        if term in all_stems:
            continue
        # Only report if it looks like a concept/entity (no path separators)
        if "/" in term or "\\" in term:
            continue
        missing_concepts.append({"term": term, "mentions": count})

    # Sync conflicts: foo.md, foo_1.md, foo_2.md
    sync_conflicts: List[dict] = []
    stem_groups: Dict[str, List[str]] = {}
    for p in md_files:
        rel = p.relative_to(wiki_root / "wiki").as_posix()
        stem = p.stem
        base = stem
        m = re.match(r"^(.+)_(\d+)$", stem)
        if m:
            base = m.group(1)
        stem_groups.setdefault(base, []).append(rel)
    for base, variants in stem_groups.items():
        if len(variants) > 1:
            # Ensure there is a base file and at least one _N variant
            base_file = f"{base}.md"
            has_base = base_file in variants
            has_variant = any(re.search(r"_\d+\.md$", v) for v in variants)
            if has_base and has_variant:
                sync_conflicts.append(
                    {
                        "base": base_file,
                        "variants": sorted(v for v in variants if v != base_file),
                    }
                )

    now = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": now,
        "summary": {
            "total_pages": len(md_files),
            "orphan_pages": len(orphan_pages),
            "missing_concepts": len(missing_concepts),
            "sync_conflicts": len(sync_conflicts),
            "empty_pages": len(empty_pages),
        },
        "orphan_pages": orphan_pages,
        "missing_concepts": missing_concepts,
        "sync_conflicts": sync_conflicts,
        "empty_pages": empty_pages,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint the llm-wiki and output a structured JSON report."
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
    report = run_lint(wiki_root)
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
