#!/usr/bin/env python3
"""
ingest_document.py

CLI script for ingesting DOCX (and other document) files into the llm-wiki raw layer.

Outputs:
  - raw/documents/{slug}.docx      (original file copy)
  - raw/documents/{slug}.meta.yaml (metadata sidecar)
  - raw/articles/{slug}.md         (converted markdown)
  - raw/images/{slug}_img_{NN}.png (extracted images)
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from document_parser import parse_docx, save_images, meta_to_yaml, DocumentMeta


def resolve_wiki_root(output_dir: Optional[Path] = None) -> Path:
    """Resolve wiki root directory."""
    if output_dir:
        return output_dir.resolve()

    # Check current directory and parents for .wiki
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        if (path / ".wiki").exists():
            return path

    # Fallback to skill directory
    skill_dir = Path(__file__).parent.parent.resolve()
    return skill_dir


def make_safe_slug(name: str) -> str:
    """Convert a filename to a safe slug."""
    import re
    slug = re.sub(r"[^\w\-]", "_", name)
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_")


def write_raw_source_markdown(
    md_path: Path,
    content: str,
    meta: DocumentMeta,
    slug: str,
    image_paths: list,
) -> None:
    """Write markdown with raw-source frontmatter for llm-wiki."""
    title = meta.title or slug
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = meta.subject or f"Auto-ingested DOCX document: {meta.filename}"

    frontmatter = f"""---
title: {title}
type: raw-source
source: file
tags:
  - document
  - docx
created: {created}
summary: {summary}
original_file: raw/documents/{slug}.docx
meta_file: raw/documents/{slug}.meta.yaml
---

"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(frontmatter)
        f.write(content)

        # Append image references at end if any
        if image_paths:
            f.write("\n\n## Extracted Images\n\n")
            for i, img_path in enumerate(image_paths):
                f.write(f"![Image {i}]({img_path})\n\n")


def update_ingest_manifest(wiki_root: Path, entry: dict) -> None:
    """Append entry to ingest_manifest.json if it exists."""
    manifest_path = wiki_root / ".wiki" / "ingest_manifest.json"
    if not manifest_path.exists():
        return

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    sources = manifest.setdefault("sources", [])
    sources.append(entry)

    tmp = manifest_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    tmp.replace(manifest_path)


def ingest_document(
    input_file: Path,
    slug: Optional[str] = None,
    output_dir: Optional[Path] = None,
    skip_manifest: bool = False,
) -> dict:
    """
    Ingest a document file into the wiki raw layer.

    Returns a dict with paths to all generated files.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Resolve paths
    wiki_root = resolve_wiki_root(output_dir)
    slug = slug or make_safe_slug(input_file.stem)

    raw_documents_dir = wiki_root / "raw" / "documents"
    raw_articles_dir = wiki_root / "raw" / "articles"
    raw_images_dir = wiki_root / "raw" / "images"

    raw_documents_dir.mkdir(parents=True, exist_ok=True)
    raw_articles_dir.mkdir(parents=True, exist_ok=True)
    raw_images_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy original file
    docx_dest = raw_documents_dir / f"{slug}.docx"

    # Handle extension for non-docx files
    if input_file.suffix.lower() != ".docx":
        docx_dest = raw_documents_dir / f"{slug}{input_file.suffix}"

    shutil.copy2(input_file, docx_dest)

    # 2. Parse document (currently only DOCX supported)
    if input_file.suffix.lower() == ".docx":
        content, meta, images = parse_docx(input_file, slug)

        # Calculate checksum and size for original file
        sha256_hash = hashlib.sha256()
        with open(input_file, "rb") as f:
            file_data = f.read()
            sha256_hash.update(file_data)
        meta.checksum = f"sha256:{sha256_hash.hexdigest()}"
        meta.size_bytes = len(file_data)

        # 3. Save images
        image_paths = []
        if images:
            image_paths = save_images(images, raw_images_dir, slug)

        # 4. Write markdown to raw/articles/
        md_dest = raw_articles_dir / f"{slug}.md"
        write_raw_source_markdown(md_dest, content, meta, slug, image_paths)

        # 5. Write meta.yaml sidecar
        meta_path = raw_documents_dir / f"{slug}.meta.yaml"
        meta_yaml = meta_to_yaml(meta, slug)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(meta_yaml)

        # 6. Optionally update manifest
        if not skip_manifest:
            entry = {
                "original": str(input_file.resolve()),
                "slug": slug,
                "raw_path": f"raw/articles/{slug}.md",
                "document_path": f"raw/documents/{docx_dest.name}",
                "meta_path": f"raw/documents/{slug}.meta.yaml",
                "status": "ingested",
                "source_type": "docx",
            }
            update_ingest_manifest(wiki_root, entry)

        return {
            "slug": slug,
            "original": str(input_file),
            "document": str(docx_dest),
            "markdown": str(md_dest),
            "meta": str(meta_path),
            "images": image_paths,
            "word_count": meta.word_count,
            "table_count": meta.table_count,
            "image_count": meta.image_count,
        }
    else:
        # For non-docx files, just copy and create minimal metadata
        meta = DocumentMeta()
        meta.filename = input_file.name
        meta.source_type = input_file.suffix.lower().lstrip(".")
        meta.title = slug

        meta_path = raw_documents_dir / f"{slug}.meta.yaml"
        meta_yaml = meta_to_yaml(meta, slug)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(meta_yaml)

        if not skip_manifest:
            entry = {
                "original": str(input_file.resolve()),
                "slug": slug,
                "document_path": f"raw/documents/{docx_dest.name}",
                "meta_path": f"raw/documents/{slug}.meta.yaml",
                "status": "copied",
                "source_type": meta.source_type,
            }
            update_ingest_manifest(wiki_root, entry)

        return {
            "slug": slug,
            "original": str(input_file),
            "document": str(docx_dest),
            "meta": str(meta_path),
            "images": [],
            "word_count": 0,
            "table_count": 0,
            "image_count": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a document into llm-wiki raw layer"
    )
    parser.add_argument("input_file", type=Path, help="Path to input document")
    parser.add_argument("--slug", type=str, help="Document slug (default: filename stem)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Wiki root directory (default: auto-resolve)",
    )
    parser.add_argument(
        "--skip-manifest",
        action="store_true",
        help="Do not update ingest_manifest.json",
    )

    args = parser.parse_args()

    try:
        result = ingest_document(
            args.input_file,
            slug=args.slug,
            output_dir=args.output_dir,
            skip_manifest=args.skip_manifest,
        )
        print(f"Ingested: {result['slug']}")
        print(f"  Original: {result['original']}")
        print(f"  Document: {result['document']}")
        if result.get("markdown"):
            print(f"  Markdown: {result['markdown']}")
        print(f"  Metadata: {result['meta']}")
        if result['images']:
            print(f"  Images:   {len(result['images'])} extracted")
        print(f"  Stats:    {result['word_count']} words, {result['table_count']} tables, {result['image_count']} images")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
