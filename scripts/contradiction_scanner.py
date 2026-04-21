#!/usr/bin/env python3
"""
contradiction_scanner.py

Scans the wiki for potential contradictions in structured fields and extracted claims.
Uses rule-based extraction to find candidates; Agent verifies semantic contradictions.

Output structured JSON with severity levels:
- high:    Frontmatter structured conflicts (dates, status, versions)
- medium:  Extracted claim mismatches (dates/versions in body text)
- low:     Potential semantic conflicts (requires Agent verification)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Patterns for extracting claims from body text
DATE_PATTERNS = [
    (r'\d{4}-\d{2}-\d{2}', 'iso_date'),                    # 2024-01-15
    (r'\d{4}/\d{2}/\d{2}', 'slash_date'),                  # 2024/01/15
    (r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}', 'text_date'),  # Jan 15, 2024
]

VERSION_PATTERNS = [
    (r'v\d+\.\d+\.\d+', 'semver'),                         # v5.10.0
    (r'v\d+\.\d+', 'short_ver'),                          # v5.10
    (r'version\s+\d+\.\d+\.?\d*', 'version_word'),         # version 2.3.1
    (r'\d+\.\d+\.\d+(?:-[a-z0-9]+)?', 'bare_semver'),      # 2.3.1-beta
]

NUMBER_PATTERNS = [
    (r'\d+\s*(?:users?|people|customers?)', 'user_count'), # 1000 users
    (r'\d+\s*(?:files?|documents?)', 'file_count'),        # 50 files
    (r'\d+\s*(?:pages?|articles?)', 'page_count'),         # 100 pages
    (r'affected[:\s]+\d+', 'affected_count'),              # affected: 1000
]

STATUS_WORDS = [
    (r'\bdeprecated\b', 'deprecated'),
    (r'\bactive\b', 'active'),
    (r'\bstable\b', 'stable'),
    (r'\bunstable\b', 'unstable'),
    (r'\bvulnerable\b', 'vulnerable'),
    (r'\bfixed\b', 'fixed'),
    (r'\bpatched\b', 'patched'),
]


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
    current_key = None
    current_list = []
    
    for line in fm_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        
        # List continuation
        if stripped.startswith('- ') and current_key:
            current_list.append(stripped[2:].strip())
            continue
        elif current_key and current_list:
            fm[current_key] = current_list
            current_list = []
            current_key = None
        
        # Key: value pair
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip().lower()
            value = value.strip()
            
            if value.startswith('[') and value.endswith(']'):
                # Inline list [a, b, c]
                items = [x.strip().strip('"\'') for x in value[1:-1].split(',')]
                fm[key] = items
            elif value:
                fm[key] = value
            else:
                current_key = key
                current_list = []
    
    if current_key and current_list:
        fm[current_key] = current_list
    
    return fm, body


def extract_context(text: str, match_start: int, context_chars: int = 50) -> str:
    """Extract surrounding context for a match."""
    start = max(0, match_start - context_chars)
    end = min(len(text), match_start + context_chars)
    context = text[start:end]
    # Clean up newlines for readability
    context = re.sub(r'\s+', ' ', context)
    return context.strip()


def normalize_date(date_str: str) -> Optional[str]:
    """Try to normalize various date formats to ISO format."""
    # Already ISO format
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return date_str[:10]
    # Slash format
    m = re.match(r'(\d{4})/(\d{2})/(\d{2})', date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def normalize_version(ver_str: str) -> str:
    """Normalize version string for comparison."""
    # Remove leading 'v' and 'version '
    ver = re.sub(r'^(v|version\s+)', '', ver_str, flags=re.I)
    return ver.lower()


def extract_claims_from_text(text: str, page_path: str) -> List[dict]:
    """Extract all verifiable claims from text."""
    claims = []
    
    for pattern, claim_type in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            normalized = normalize_date(match.group())
            if normalized:
                claims.append({
                    "type": "date",
                    "subtype": claim_type,
                    "value": normalized,
                    "raw": match.group(),
                    "context": extract_context(text, match.start()),
                    "position": match.start(),
                })
    
    for pattern, claim_type in VERSION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "type": "version",
                "subtype": claim_type,
                "value": normalize_version(match.group()),
                "raw": match.group(),
                "context": extract_context(text, match.start()),
                "position": match.start(),
            })
    
    for pattern, claim_type in NUMBER_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            num = re.search(r'\d+', match.group())
            if num:
                claims.append({
                    "type": "number",
                    "subtype": claim_type,
                    "value": int(num.group()),
                    "raw": match.group(),
                    "context": extract_context(text, match.start()),
                    "position": match.start(),
                })
    
    for pattern, status in STATUS_WORDS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "type": "status",
                "value": status,
                "raw": match.group(),
                "context": extract_context(text, match.start()),
                "position": match.start(),
            })
    
    return claims


def find_all_pages(wiki_root: Path) -> Dict[str, Path]:
    """Find all markdown pages in wiki."""
    pages: Dict[str, Path] = {}
    
    for subdir in ["wiki", "raw/articles"]:
        target = wiki_root / subdir
        if target.exists():
            for p in target.rglob("*.md"):
                if p.is_file():
                    pages[p.stem] = p
    
    return pages


def get_entity_key(path: Path, frontmatter: dict) -> Optional[str]:
    """Determine the entity key for grouping related pages."""
    # Priority 1: explicit entity/title in frontmatter
    if 'title' in frontmatter:
        return frontmatter['title']
    if 'entity' in frontmatter:
        return frontmatter['entity']
    
    # Priority 2: filename stem
    return path.stem


def check_frontmatter_contradictions(
    all_pages: Dict[str, Path]
) -> List[dict]:
    """Check for contradictions in structured frontmatter fields."""
    conflicts = []
    
    # Group by entity
    entity_data: Dict[str, List[dict]] = defaultdict(list)
    
    for stem, path in all_pages.items():
        try:
            text = path.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
        except (UnicodeDecodeError, OSError):
            continue
        
        entity = get_entity_key(path, fm) or stem
        
        entity_data[entity].append({
            "stem": stem,
            "path": str(path),
            "frontmatter": fm,
        })
    
    # Check for conflicts within each entity
    for entity, pages in entity_data.items():
        if len(pages) < 2:
            continue
        
        # Check created dates
        created_dates = set()
        for p in pages:
            if 'created' in p['frontmatter']:
                created_dates.add((p['stem'], p['frontmatter']['created']))
        
        if len(created_dates) > 1:
            dates = [d for _, d in created_dates]
            if len(set(dates)) > 1:  # Different values
                conflicts.append({
                    "severity": "high",
                    "type": "date_conflict",
                    "subtype": "created_date",
                    "entity": entity,
                    "message": f"Entity '{entity}' has multiple created dates",
                    "locations": [
                        {"page": stem, "date": date} for stem, date in created_dates
                    ],
                })
        
        # Check status conflicts
        statuses = []
        for p in pages:
            if 'status' in p['frontmatter']:
                statuses.append((p['stem'], p['frontmatter']['status']))
        
        if len(statuses) > 1:
            # Check for contradictory statuses
            status_set = set(s.lower() for _, s in statuses)
            contradictory_pairs = [
                ({'active', 'deprecated'}, "Entity cannot be both active and deprecated"),
                ({'stable', 'unstable'}, "Entity cannot be both stable and unstable"),
                ({'vulnerable', 'fixed'}, "Entity cannot be both vulnerable and fixed"),
            ]
            
            for pair, message in contradictory_pairs:
                if pair <= status_set:
                    conflicts.append({
                        "severity": "high",
                        "type": "status_conflict",
                        "entity": entity,
                        "message": message,
                        "locations": [
                            {"page": stem, "status": status} for stem, status in statuses
                            if status.lower() in pair
                        ],
                    })
    
    return conflicts


def check_claim_contradictions(
    all_pages: Dict[str, Path]
) -> List[dict]:
    """Check for contradictions in extracted claims from body text."""
    conflicts = []
    
    # Extract all claims grouped by entity
    entity_claims: Dict[str, List[dict]] = defaultdict(list)
    
    for stem, path in all_pages.items():
        try:
            text = path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
        except (UnicodeDecodeError, OSError):
            continue
        
        entity = get_entity_key(path, fm) or stem
        claims = extract_claims_from_text(body, str(path))
        
        for claim in claims:
            entity_claims[entity].append({
                "page": stem,
                "path": str(path),
                **claim,
            })
    
    # Check for conflicts within each entity
    for entity, claims in entity_claims.items():
        # Group by claim type
        by_type: Dict[str, List[dict]] = defaultdict(list)
        for c in claims:
            key = f"{c['type']}:{c.get('subtype', '')}"
            by_type[key].append(c)
        
        for type_key, type_claims in by_type.items():
            if len(type_claims) < 2:
                continue
            
            # Check for different values
            values = [c['value'] for c in type_claims]
            if len(set(str(v) for v in values)) > 1:
                # Potential conflict - but need Agent to verify if it's real
                claim_type = type_key.split(':')[0]
                conflicts.append({
                    "severity": "medium",
                    "type": "claim_mismatch",
                    "claim_type": claim_type,
                    "entity": entity,
                    "message": f"Entity '{entity}' has multiple {claim_type} values in different pages",
                    "values": list(set(str(v) for v in values)),
                    "locations": [
                        {
                            "page": c['page'],
                            "value": c['value'],
                            "context": c['context'],
                        }
                        for c in type_claims
                    ],
                    "note": "Agent should verify if these are real contradictions or represent different aspects",
                })
    
    return conflicts


def run_scan(wiki_root: Path) -> dict:
    """Run the full contradiction scan."""
    all_pages = find_all_pages(wiki_root)
    
    # Check structured frontmatter (high confidence)
    frontmatter_conflicts = check_frontmatter_contradictions(all_pages)
    
    # Check extracted claims (medium confidence, needs Agent verification)
    claim_conflicts = check_claim_contradictions(all_pages)
    
    all_conflicts = frontmatter_conflicts + claim_conflicts
    
    # Separate by severity
    high_priority = [c for c in all_conflicts if c['severity'] == 'high']
    medium_priority = [c for c in all_conflicts if c['severity'] == 'medium']
    
    now = datetime.now(timezone.utc).isoformat()
    
    return {
        "generated_at": now,
        "tool": "contradiction_scanner.py",
        "summary": {
            "total_pages": len(all_pages),
            "high_priority_conflicts": len(high_priority),
            "medium_priority_conflicts": len(medium_priority),
            "total_conflicts": len(all_conflicts),
        },
        "high_priority": high_priority,  # Agent should fix these
        "medium_priority": medium_priority,  # Agent should verify these
        "scan_parameters": {
            "date_patterns": len(DATE_PATTERNS),
            "version_patterns": len(VERSION_PATTERNS),
            "number_patterns": len(NUMBER_PATTERNS),
            "status_words": len(STATUS_WORDS),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan for potential contradictions in wiki content."
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
    report = run_scan(wiki_root)
    report_json = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"Contradiction scan report written to {args.output}")
        s = report["summary"]
        print(f"\nSummary: {s['total_pages']} pages scanned")
        if s['high_priority_conflicts']:
            print(f"  🔴 High priority: {s['high_priority_conflicts']} (auto-fix recommended)")
        if s['medium_priority_conflicts']:
            print(f"  🟡 Medium priority: {s['medium_priority_conflicts']} (Agent verification needed)")
        if s['total_conflicts'] == 0:
            print("  🟢 No contradictions detected!")
    else:
        print(report_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
