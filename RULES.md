# LLM Wiki Rules

This file contains the execution rules for the `llm-wiki` skill.
Every time this skill is invoked, the agent MUST read this file first.

---

## First Principle

The wiki is a **persistent, compounding artifact**. Every ingest and every filed query makes it richer. Cross-references are pre-built. Contradictions are pre-flagged. The knowledge is compiled once and kept current — not re-derived on every query.

---

## Wiki Root Resolution

The effective wiki root directory is resolved in this precedence:
1. The output of `python scripts/configure.py` (reads skill-level `config.json`, then project-level `.wiki/config.json`).
2. If `configure.py` has not been run, read `.wiki/config.json` in the current workspace.
3. Fallback: the `.wiki` folder under the skill directory itself (persists across sessions).

All `/wiki` commands and scripts operate relative to this resolved wiki root.

> **Initialization hint:** When you run `/wiki init`, the agent will tell you which wiki directory is active. To change the global default, edit the skill-level `config.json`. To use a different wiki for a single project, create `project_dir/.wiki/config.json` and set `wiki_dir` there.

## Directory Structure

```
raw/
  articles/           # Markdown sources (converted from web or documents)
  documents/          # Original binary files (docx, pdf, etc.) — immutable
    {slug}.docx
    {slug}.meta.yaml  # Sidecar metadata with checksum & element index
  images/             # Extracted images from documents
    {slug}_img_{NN}.png
wiki/
  concepts/
  entities/
  sources/
  queries/
  comparisons/
  index.md
  log.md
```

**Three-layer data model:**
- **Layer 1 (Truth):** `raw/documents/` — original files, never modified.
- **Layer 2 (Readable):** `raw/articles/` — markdown conversions for LLM consumption.
- **Layer 3 (Knowledge):** `wiki/` — extracted concepts, entities, summaries, and filed queries.

## Quick Reference

| Command | Action |
|---------|--------|
| `/wiki init` | Run configuration script to resolve and validate the wiki directory |
| `/wiki ingest <path>` or `ingest <topic>` | Search web → save to raw/ OR ingest local document → compile into wiki |
| `/wiki ingest-doc <path>` | Ingest a local document (docx) into raw layer |
| `/wiki query "<question>"` | Search wiki and synthesize an answer (auto-saved to wiki) |
| `/wiki lint` | Health-check the wiki for contradictions, orphans, gaps |
| `/wiki sync` | Scan `.learning` and project `.wiki` dirs → stage/sync → auto-ingest into wiki |

<!-- CONFIGURE_START -->
> **Auto-configured wiki directory:** resolved dynamically by `configure.py`.
>
> Global default comes from the skill-level `config.json`. Project-level `.wiki/config.json` overrides it. Run `configure.py` to get the active wiki directory for the current project.
<!-- CONFIGURE_END -->

---

## Autonomy Principles

- The Agent resolves contradictions autonomously and notes them in `wiki/log.md`.
- The Agent commits changes directly without asking when `.wiki/config.json` has `auto_commit: true`.
- The Agent files every query answer automatically without prompting the user.
- The Agent applies lint fixes directly and reports what was changed.
- The Agent decides the best page structure, cross-link targets, and output format within the constraints below.

---

## Ingest Workflow

**Trigger:** User provides a specific path/URL, OR asks to "搜集/查找/研究 [topic] 相关的资料/知识/方法/解决方案" without providing a path.

### Goal
Acquire the source, extract its knowledge, and expand the wiki with new or updated concept pages, entity pages, a source summary, and cross-links.

### Agent responsibilities
- Determine whether the source is local (read directly) or remote (search and download).
- Save raw sources to `raw/articles/YYYY-MM-DD-topic.md` with the raw-source frontmatter when remote.
- Read `wiki/index.md` to understand the current structure before creating pages.
- On first ingest (empty wiki), skip contradiction checks.
- On subsequent ingests, compare the new source against existing wiki claims (dates, numbers, definitions, rankings). Resolve contradictions autonomously and note them in `wiki/log.md`.
- Create or update pages without asking the user for approval.

### Output requirements
- A **summary page** in `wiki/sources/YYYY-MM-DD-slug.md`.
- **Concept pages** in `wiki/concepts/` (typically 3-6 per source).
- **Entity pages** in `wiki/entities/` (people, organizations, tools, CVEs, malware families, etc.).
- `[[wiki-link]]` cross-links in the **body text** of every new/updated page (Obsidian only recognizes wiki-links in the body, not in frontmatter). Keep `related:` frontmatter as plain-text list for Dataview queries.
- Updated `wiki/index.md` and `wiki/overview.md` (if domain synthesis has shifted).
- An appended entry in `wiki/log.md`.

### You MAY
- Use `websearch` or `webfetch` for remote sources.
- Use `edit` instead of `write` when updating existing pages.
- Generate Mermaid diagrams or comparison tables inside concept pages when helpful.

### You MUST NOT
- Write to `raw/` after the initial staging of a remote source.
- Skip frontmatter on wiki pages.
- Skip cross-linking.
- Ask the user for permission before writing pages.

---

## Document Ingest Workflow

**Trigger:** User provides a local document file (`.docx`).

### Goal
Convert the document to markdown while preserving the original file, then feed it into the standard Ingest Workflow.

### Agent responsibilities
- Determine if the file is `.docx` (supported) or another format.
- Run the parser:
  ```bash
  python scripts/ingest_document.py <path> --slug <slug> --output-dir <wiki-root>
  ```
- The script handles:
  - Copying the original file to `raw/documents/{slug}.docx`
  - Converting text, headings, tables to markdown → `raw/articles/{slug}.md`
  - Extracting images → `raw/images/{slug}_img_{NN}.png`
  - Generating `raw/documents/{slug}.meta.yaml` with SHA256 checksum and element index
- **Handle missing metadata gracefully:** If `author` is missing, don't invent "Un-named". If `title` is missing, use the filename. Work with what the document provides.
- After conversion, proceed with the standard Ingest Workflow on the generated markdown.

### Document conversion rules
- **Headings:** Preserved as `#`, `##`, `###`, etc.
- **Tables:** Converted to markdown tables. Merged cells are split into individual cells; merged content is placed in the first (top-left) cell. A note is appended below the table.
- **Images:** Extracted and saved. Inline position is recorded in `meta.yaml` (v1 appends images at the end of the markdown; see Meta Sidecar for position tracking).
- **Data integrity:** `meta.yaml` contains `source.checksum` (SHA256) and `source.size_bytes`. If these don't match the original file, re-conversion may be needed.
- **Best-effort extraction:** Document metadata (author, title, creation date) is extracted when available. Many documents lack these properties. The parser falls back to filename-derived titles and omits missing fields rather than inventing placeholder values.

### Output requirements
- `raw/documents/{slug}.docx` — original file (immutable).
- `raw/documents/{slug}.meta.yaml` — metadata sidecar with checksum and element index. Optional fields may be omitted.
- `raw/articles/{slug}.md` — markdown with `raw-source` frontmatter. Missing metadata fields are omitted, not invented.
- `raw/images/{slug}_img_{NN}.png` — extracted images.

### You MAY
- Run `ingest_document.py` directly or via `/wiki ingest <path>` when the path points to a `.docx` file.
- Inspect `meta.yaml` to verify conversion completeness.

### You MUST NOT
- Modify the original file in `raw/documents/`.
- Delete `meta.yaml` — it is required for data integrity verification and secondary extraction.
- Ask the user for permission before running document conversion.

---

## Query & File Workflow

**Trigger:** user asks any question against the wiki.

### Goal
Synthesize an answer from the wiki, cite sources with `[[wiki-link]]`, and file the result automatically.

### Agent responsibilities
- Read `wiki/index.md`, then `grep` or `read` relevant pages (and raw sources if needed).
- Synthesize an answer in the most useful form: markdown page, comparison table, Mermaid diagram, or chart.
- Save the answer without prompting the user.

### Output requirements
- A saved answer at `wiki/queries/YYYY-MM-DD-slug.md` (or `wiki/comparisons/` for tables).
- Frontmatter with `type: query-answer` or `type: comparison`, `question: "..."`, and `sources: [...]`.
- `[[wiki-link]]` citations in the **body text**. Keep `related:` frontmatter as plain-text list for Dataview queries.
- Updated `wiki/index.md` and `wiki/log.md`.

### You MAY
- Pull in raw sources if the wiki pages are insufficient.
- Structure the answer as a table or diagram when that improves clarity.

### You MUST NOT
- Ask whether to file the answer — filing is mandatory.
- Omit citations.

---

## Lint Workflow

**Trigger:** user says "lint wiki" or `/wiki lint`

### Goal
Produce a structured health report and fix issues autonomously.

### Agent responsibilities
- Run `wiki_lint.py` to generate a structured report.
- Run `wiki_link_checker.py` to detect broken links, orphans, and missing backlinks.
- Run `contradiction_scanner.py` to find frontmatter conflicts and claim mismatches.
- Read all reports and fix identified issues autonomously.
- For link issues: fix broken links, add missing cross-links, or create missing pages.
- For contradictions: resolve high-priority conflicts directly; verify medium-priority with context.
- Flag any remaining issues and suggest new questions or sources to investigate.
- For sync conflicts (e.g., `foo.md` + `foo_1.md`), decide whether merging is appropriate.

### Output requirements
- A combined markdown lint report presented to the user.
- The report appended to `wiki/log.md`.
- Any auto-fixes applied to the wiki directly.

### You MAY
- Use `wiki_link_checker.py` and `contradiction_scanner.py` during lint.
- Use `grep` to assist if the scripts are unavailable.
- Propose new concept pages or sources to ingest based on findings.
- Auto-merge sync conflicts when the relationship between variants is unambiguous.

### You MUST NOT
- Present findings without also appending them to `wiki/log.md`.
- Silently delete content during a sync-conflict merge without logging what was preserved.

---

## Frontmatter Templates

**Wiki pages:**
```yaml
---
title: Page Title
type: concept | entity | source-summary | comparison | query-answer
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
sources:
  - raw/...
related:
  - concept-name
  - entity-name
---
```

**Body cross-links (Obsidian-compatible):**
```markdown
## Related
- [[concept-name]]
- [[entity-name]]
```

> **Note:** Obsidian only parses `[[wiki-link]]` syntax in the markdown body, not inside YAML frontmatter. Always place clickable wiki-links in the body, and keep `related:` frontmatter as plain text for Dataview or programmatic use.

**Raw sources (from document files):**
```yaml
---
title: Document Title                    # Required: from doc properties or filename
type: raw-source
source: file                             # Required: distinguishes from web sources
source_format: docx                      # Required: file extension
slug: my-report                          # Optional: URL-safe identifier
created: YYYY-MM-DD                      # Required: ingestion date
original_file: raw/documents/...         # Required: path to immutable original
meta_file: raw/documents/...             # Optional: path to sidecar metadata
summary: One-line description            # Optional: auto-generated or manual
tags:                                    # Optional: inferred from content
  - document
  - docx
# Additional fields extracted when available:
# author: "Author Name"                  # From document properties (may be missing)
# modified: YYYY-MM-DD                   # From file modification time
---
```

**Notes on document frontmatter:**
- `title`: Falls back to filename if document has no title property
- `author`: Often missing in practice; omitted if unknown rather than "Un-named"
- `summary`: Auto-generated from first paragraph or user-provided
- Fields are additive: as parser improves, more properties may be extracted

**Raw sources (from web):**
```yaml
---
title: Source Title
type: raw-source
source: web_search | url
tags: [topic1, topic2]
created: YYYY-MM-DD
summary: One-line description of the source
---
```

---

## index.md Format

```markdown
# Wiki Index

## Concepts
- [[concept-name]] — One-line summary (N sources)

## Entities
- [[entity-name]] — One-line summary (N sources)

## Source Summaries
- [[summary-name]] — YYYY-MM-DD

## Comparisons
- [[comparison-name]] — Filed from query YYYY-MM-DD

## Query Answers
- [[query-name]] — Filed from query YYYY-MM-DD
```

---

## Meta Sidecar Format

For each ingested document, a metadata sidecar is generated alongside the original file in `raw/documents/`.

### Purpose
- **Data integrity:** SHA256 checksum and file size for detecting tampering or corruption.
- **Element index:** A map of every paragraph, table, image, and heading extracted during conversion.
- **Future-proofing:** Enables secondary extraction, incremental updates, or re-conversion with improved parsers.

### Schema (flexible, versioned)

```yaml
title: "Document Title"          # From doc properties or filename
slug: "doc-slug"                 # URL-safe identifier
type: document                   # Fixed type
source_type: docx                # Original format

source:                          # Original file info
  path: "raw/documents/..."
  checksum: "sha256:..."         # Format: "algorithm:value"
  size_bytes: 12345
  # mtime: "2026-01-01T00:00:00"  # Optional: file modification time

conversion:                      # Conversion metadata
  timestamp: "2026-01-01T00:00:00+00:00"
  tool: "document_parser.py"
  # markdown: "raw/articles/..."  # Optional: path to generated markdown
  # images_dir: "raw/images/"     # Optional: images directory

stats:                           # Content statistics
  word_count: 102
  paragraph_count: 52
  table_count: 0
  image_count: 3
  # heading_count: 5            # Optional

elements:                        # Structural elements (format may vary by tool version)
  tables: []                     # List of extracted tables
  images:                        # List of extracted images
    - index: 0
      file: "raw/images/..."
      context: "Description of where image appeared"
  # headings: []                # Optional: heading structure
  # paragraphs: []              # Optional: paragraph index

# Optional fields extracted when available:
# author: "Author Name"         # From document metadata (often missing)
# tags: []                      # Auto-inferred tags
# created: "2026-01-01"         # From document properties
# modified: "2026-01-01"        # From document properties
```

### Versioning notes

- **No `version` field currently**: The schema evolves; parsers should handle missing fields gracefully.
- **Field presence varies**: Depending on document format and parser capabilities, some fields may be absent.
- **Checksum format**: Currently `sha256:hex`, may support other algorithms in future.
- **Element structure**: The `elements` object format may change between parser versions; use defensively.

---

## Log Entry Format

Append to `wiki/log.md`:

```markdown
## [YYYY-MM-DD] ingest | Source Title
- Source: `raw/...`
- Pages created: `wiki/sources/...`, `wiki/concepts/...`
- Pages updated: `wiki/entities/...`, `wiki/index.md`
- Notes: any contradictions or flags

## [YYYY-MM-DD] query | Filed Answer
- Question: "..."
- Output: `wiki/queries/...`
- Pages read: `wiki/concepts/...`, `wiki/sources/...`

## [YYYY-MM-DD] lint | Health Check
- Contradictions: N
- Orphan pages: N
- Missing pages suggested: N
- Investigations suggested: N
```

---

## Automated Checking Tools

This skill provides two specialized checking tools to maintain wiki quality:

### wiki_link_checker.py

Checks for link-related issues across the wiki.

**Usage:**
```bash
python scripts/wiki_link_checker.py --wiki-root ./.wiki
```

**Detects:**
- **Broken links**: `[[target]]` where target page doesn't exist
- **Orphan pages**: Pages with no incoming links
- **Missing backlinks**: A links to B but B doesn't link back to A
- **Isolated pages**: Pages with no outgoing links

**Report format:**
```json
{
  "broken_links": [{"from": "page", "to": "missing", "line": 12}],
  "orphan_pages": [{"stem": "unlinked", "path": "wiki/concepts/..."}],
  "missing_backlinks": [{"from": "a", "to": "b"}]
}
```

**Agent action:**
- Fix broken links (correct typo or create target page)
- Add cross-links to orphan pages
- Consider adding backlinks for bidirectional relationships

### contradiction_scanner.py

Scans for potential contradictions in structured data and extracted claims.

**Usage:**
```bash
python scripts/contradiction_scanner.py --wiki-root ./.wiki
```

**Detects:**

**High priority (structured frontmatter):**
- Same entity with different `created` dates
- Conflicting statuses (active + deprecated, vulnerable + fixed)

**Medium priority (extracted body claims):**
- Different version numbers mentioned for same entity
- Different dates or numbers in different contexts

**Report format:**
```json
{
  "high_priority": [
    {
      "severity": "high",
      "type": "date_conflict",
      "entity": "...",
      "locations": [{"page": "a", "date": "2024-01"}, {"page": "b", "date": "2024-03"}]
    }
  ],
  "medium_priority": [
    {
      "severity": "medium", 
      "type": "claim_mismatch",
      "claim_type": "version",
      "note": "Agent should verify if these are real contradictions"
    }
  ]
}
```

**Agent action:**
- **High priority**: Fix directly (structured data conflicts are almost always real)
- **Medium priority**: Verify with context (may be different components: "PHP 8.2" vs "MySQL 5.7" are not contradictions)
- Add clarifying notes if different values represent different aspects

### Integration with /wiki lint

During `/wiki lint`, the Agent should:

1. Run all three checkers:
   ```bash
   python scripts/wiki_lint.py --wiki-root ./.wiki -o /tmp/lint.json
   python scripts/wiki_link_checker.py --wiki-root ./.wiki -o /tmp/links.json
   python scripts/contradiction_scanner.py --wiki-root ./.wiki -o /tmp/contra.json
   ```

2. Read all reports and synthesize a combined action plan

3. Fix high-confidence issues autonomously

4. Flag medium-priority items for user review or add clarifying context

5. Append summary to `wiki/log.md`

---

## Tool Stack (Optional)

At small scale, `index.md` + OpenCode's built-in `grep`/`read` is sufficient. As the wiki grows, consider:

| Tool | Purpose | When to Add |
|------|---------|-------------|
| **Obsidian** | IDE for browsing the wiki, graph view, backlinks | From day one (recommended) |
| **Obsidian Web Clipper** | Clip web articles directly to `raw/` | For web-based sources |
| **qmd** | Hybrid BM25/vector search for markdown | When index.md exceeds comfortable context-window size (~100+ sources) |
| **Dataview** | Query frontmatter inside Obsidian | When you want dashboards (tags, source counts, stale pages) |
| **python-docx** | Parse .docx documents and extract text/tables/images | When ingesting local documents |
| **wiki_link_checker.py** | Check for broken wiki-links, orphans, missing backlinks | Run during /wiki lint or as pre-commit check |
| **contradiction_scanner.py** | Scan for date/version/status conflicts in frontmatter and body | Run during /wiki lint for Agent verification |
| **Mermaid** | Diagrams and flowcharts inside markdown | For visualizing processes, architectures, or relationships |
| **Git** | Version control | From day one (recommended) |

> **Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase.**

---

## Rules

- **NEVER write to `raw/documents/`**. It is the immutable truth layer; originals are never modified.
- **Always use frontmatter** on new wiki pages.
- **Always cross-link** with `[[wiki-link]]` syntax in the **body text** of every new/updated page. Also list related pages in the `related:` frontmatter as plain text (for Dataview queries).
- **Always log** every ingest, query-filing, and lint pass.
- Prefer `edit` over `write` when updating existing pages.
- **Cross-linking is easily skipped** — when creating/updating a page, always `read` `wiki/index.md` first and add `[[wiki-link]]` citations to relevant existing pages in the **body text**. Treat it as mandatory, not optional.
- **Co-evolve the schema:** As you discover what works, update `OPENCODE.md` with new conventions, page types, and workflows.
- **Execute autonomously:** Do not ask the user for permission before writing wiki pages, filing query answers, or committing when `auto_commit: true` is set in `.wiki/config.json`.
- **For documents:** After conversion, immediately run the standard Ingest Workflow on the generated markdown. Do not leave converted documents un-ingested.
- **For documents:** If the original file or its `meta.yaml` is missing, treat it as a data integrity issue and flag it in `wiki/log.md`.

---

## Auto-Ingest from `.learning` Directories

This skill ships with a companion script in `scripts/learning_scanner.py`.
It is designed to run across agent products (Claude Code, Codex, Trae, Kimi Code, CodeBuddy, etc.) that store learning data in `.learning` directories.

### What it does
1. Scans the filesystem for all `.learning` directories.
2. Maintains a persistent JSON index of files and their MD5 hashes.
3. Detects **new** and **changed** files since the last scan.
4. Outputs a JSON report of files that need ingestion.

### How to use
```bash
python scripts/learning_scanner.py --wiki-root ./wiki --output changed_files.json
```

### `/wiki sync` Workflow

**Trigger:** user says `/wiki sync`, "sync learnings", "ingest from .learning", or the agent runs its startup hook.

This workflow bridges both `.learning` directories (e.g., from self-improvement skill) and project-level `.wiki` directories into the total wiki automatically.

#### Goal
Stage new or changed `.learning` files, sync project `.wiki` directories, and ingest staged sources into the total wiki.

#### Agent responsibilities
- Run the scanner with auto-stage:
  ```bash
  python scripts/learning_scanner.py --wiki-root <path> --auto-stage
  ```
- Read `.wiki/ingest_manifest.json`. If no `.learning` sources were staged, finish after the scanner step.
- For each staged `.learning` source, execute the standard Ingest Workflow.
- `.wiki` files do NOT need ingestion; they are already in place.

#### Output requirements
- `.learning` files staged into `raw/articles/YYYY-MM-DD-{safe_slug}.md` with `raw-source` frontmatter.
- `.wiki` files (`raw/` and `wiki/` only) copied into the corresponding directories under the total wiki.
- A batch log entry appended to `wiki/log.md`.

#### You MAY
- Skip ingestion if the manifest is empty.
- Let the scanner auto-rename conflicting `.wiki` files to `foo_1.md`, `foo_2.md`, etc.

#### You MUST NOT
- Delete existing wiki files during sync.
- Skip logging the batch operation.

### `.wiki` synchronization details

- **Scope:** Only `raw/` and `wiki/` subdirectories inside a project's `.wiki` are synced. Metadata files (`doc_index.json`, `ingest_manifest.json`, etc.) are skipped.
- **Mode:** Incremental by default. Use `--wiki-full-sync` to force a full re-copy of all `.wiki` files.
- **Deletion:** Removed source files are **not** deleted from the total wiki. Use `/wiki lint` to detect and clean up stale or duplicate content.
- **Conflicts:** When two projects have the same relative path (e.g., `wiki/concepts/foo.md`), the second one is renamed to `foo_1.md`, `foo_2.md`, etc. in the total wiki.

### Naming collisions across multiple `.learning` directories

The scanner handles this automatically. The `safe_slug` is derived from:
- the parent directory name of `.learning` (relative to scan root)
- plus the relative path inside `.learning`
- joined by `__`

Example:
| Original path | Staged raw file |
|---------------|-----------------|
| `project-a/.learning/error-handling.md` | `raw/articles/2026-04-16-project-a__error-handling.md` |
| `project-b/.learning/error-handling.md` | `raw/articles/2026-04-16-project-b__error-handling.md` |

If a collision still occurs (rare edge case), a short MD5 suffix is appended.

### Handling document files in `.learning`

If `.learning` directories contain `.docx` files, the scanner or agent should:

1. Run `ingest_document.py` on each `.docx` file:
   ```bash
   python scripts/ingest_document.py /path/to/file.docx --slug <slug> --output-dir <wiki-root>
   ```
2. The script will create:
   - `raw/documents/{slug}.docx` (copy of original)
   - `raw/documents/{slug}.meta.yaml` (checksum + element index)
   - `raw/articles/{slug}.md` (markdown conversion)
   - `raw/images/{slug}_img_{NN}.png` (extracted images)
3. Then proceed with the standard Ingest Workflow on the generated markdown.

**Note:** Document files are not simply copied like markdown files. They must be converted through the document ingest pipeline to be usable.

### Periodic scanning

You can schedule the scanner via cron, a background job, or your agent's startup hook:
```bash
# Example: run every hour
0 * * * * python /path/to/scripts/learning_scanner.py --wiki-root /path/to/wiki --auto-stage
```

For agents that support startup hooks (e.g., shell profile, IDE init script), add:
```bash
python /path/to/scripts/learning_scanner.py --wiki-root /path/to/wiki --auto-stage --output /tmp/wiki_sync_report.json
```
Then have the agent read `/tmp/wiki_sync_report.json` (or `.wiki/ingest_manifest.json`) on startup and auto-trigger `/wiki sync` if sources were staged.

---

## Multi-Agent Product Adaptation Notes

This skill is intentionally decoupled from OpenCode-specific mechanics so it can be used in Claude Code, Codex, Trae, Kimi Code, CodeBuddy, and similar agents.

### What changes per product
| Concern | Adaptation |
|---------|------------|
| **Rule enforcement** | Ensure the agent reads `RULES.md` before executing any `/wiki` command. In products that support system prompts or pre-instruction hooks, prepend: "Before executing llm-wiki, read RULES.md." |
| **Tool names** | `read`, `grep`, `edit`, `write` may be called differently (e.g., `@file`, `!read`, or native IDE search). The concepts remain the same—use the product's closest equivalent. |
| **Workspace root** | Some agents run inside a project directory; others run globally. Pass `--wiki-root` explicitly when calling the scanner script. |
| **Cron / background jobs** | Not all agents support scheduling. Fallback: run the scanner at agent startup, or expose a manual `/wiki sync` command. |
| **`.learning` location** | The scanner searches recursively. If an agent stores learnings under a different name (e.g., `.memory`, `.knowledge`), change the target directory name in `learning_scanner.py`. |
| **`.wiki` aggregation** | Project-level `.wiki` directories are synced directly into the total wiki (`raw/` → `raw/`, `wiki/` → `wiki/`). Conflicting filenames are auto-renamed (`foo_1.md`, `foo_2.md`, etc.). |

### Recommended porting checklist
- [ ] Copy `SKILL.md`, `RULES.md`, and `scripts/learning_scanner.py` into the skill/plugin directory of the target agent.
- [ ] Register `/wiki ingest`, `/wiki query`, `/wiki lint`, and `/wiki sync` as commands (or aliases).
- [ ] Configure the agent to read `RULES.md` before handling any `/wiki` command.
- [ ] Test one manual ingest and one `.learning` sync end-to-end.
- [ ] Set up periodic scanning if the product supports background tasks.

(End of file)
