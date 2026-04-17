---
name: llm-wiki
description: "Karpathy-style LLM Wiki pattern for OpenCode. Ingest raw sources into a structured, interlinked markdown wiki, and file query answers back into the knowledge base."
trigger: /wiki
metadata:
---

> **Before executing any workflow below, you MUST first read `RULES.md` in this skill directory.**

# LLM Wiki Skill

> **First Principle:** The wiki is a **persistent, compounding artifact**. Every ingest and every filed query makes it richer. Cross-references are pre-built. Contradictions are pre-flagged. The knowledge is compiled once and kept current — not re-derived on every query.

## Wiki Root Resolution

The effective wiki root directory is resolved in this precedence:
1. The output of `python scripts/configure.py` (reads skill-level `config.json`, then project-level `.wiki/config.json`).
2. If `configure.py` has not been run, read `.wiki/config.json` in the current workspace.
3. Fallback: `./.wiki` under the current working directory.

All `/wiki` commands and scripts operate relative to this resolved wiki root.

This skill implements the three-layer LLM Wiki architecture (raw / wiki / schema) inside OpenCode.

## Quick Reference

| Command | Action |
|---------|--------|
| `/wiki init` | Run configuration script to resolve and validate the wiki directory |
| `/wiki ingest <path>` or `ingest <topic>` | Search web → save to `raw/` → compile into wiki |
| `/wiki query "<question>"` | Search wiki and synthesize an answer (auto-saved to wiki) |
| `/wiki lint` | Health-check the wiki for contradictions, orphans, gaps |
| `/wiki sync` | Scan `.learning` and project `.wiki` dirs → stage/sync → auto-ingest into wiki |

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
- `[[wiki-link]]` cross-links in `related:` frontmatter and body text on every new/updated page.
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
- `[[wiki-link]]` citations in `related:` frontmatter and body.
- Updated `wiki/index.md` and `wiki/log.md`.

### You MAY
- Pull in raw sources if the wiki pages are insufficient.
- Structure the answer as a table or diagram when that improves clarity.

### You MUST NOT
- Ask whether to file the answer — filing is mandatory.
- Omit citations.

---

## Sync Workflow

**Trigger:** user says `/wiki sync`, "sync learnings", "ingest from .learning", or the agent runs its startup hook.

### Goal
Bridge `.learning` directories and project `.wiki` directories into the total wiki automatically.

### Agent responsibilities
- Run the scanner with auto-stage:
  ```bash
  python scripts/learning_scanner.py --wiki-root <path> --auto-stage
  ```
- Read `.wiki/ingest_manifest.json`. If no `.learning` sources were staged, finish after the scanner step.
- For each staged `.learning` source, execute the standard Ingest Workflow.
- `.wiki` files do NOT need ingestion; they are already in place.

### Output requirements
- `.learning` files staged into `raw/articles/YYYY-MM-DD-{safe_slug}.md` with `raw-source` frontmatter.
- `.wiki` files (`raw/` and `wiki/` only) copied into the corresponding directories under the total wiki.
- A batch log entry appended to `wiki/log.md`.

### You MAY
- Skip ingestion if the manifest is empty.
- Let the scanner auto-rename conflicting `.wiki` files to `foo_1.md`, `foo_2.md`, etc.

### You MUST NOT
- Delete existing wiki files during sync.
- Skip logging the batch operation.

---

## Lint Workflow

**Trigger:** user says "lint wiki" or `/wiki lint`

### Goal
Produce a structured health report and fix issues autonomously.

### Agent responsibilities
- Run `wiki_lint.py` to generate a structured report.
- Read the report and fix identified issues autonomously.
- Flag any contradictions, orphans, stale claims, or missing concept pages.
- Suggest new questions to investigate and new sources to look for.
- For sync conflicts (e.g., `foo.md` + `foo_1.md`), the Agent decides whether merging is appropriate. If the variants are clearly related, the Agent may auto-merge them into the base file and update `[[wiki-link]]` references accordingly. If uncertain, flag the conflict in the report and wait for user direction.

### Output requirements
- A markdown lint report presented to the user.
- The report appended to `wiki/log.md`.
- Any auto-fixes applied to the wiki directly.

### You MAY
- Use `grep` to assist contradiction and orphan detection if `wiki_lint.py` is unavailable.
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
  - [[...]]
---
```

**Raw sources:**
```yaml
---
title: Source Title
type: raw-source
source: web_search | url | file
tags: 
  - topic1
  - topic2
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

## Tool Stack (Optional)

At small scale, `index.md` + OpenCode's built-in `grep`/`read` is sufficient. As the wiki grows, consider:

| Tool | Purpose | When to Add |
|------|---------|-------------|
| **Obsidian** | IDE for browsing the wiki, graph view, backlinks | From day one (recommended) |
| **Obsidian Web Clipper** | Clip web articles directly to `raw/` | For web-based sources |
| **qmd** | Hybrid BM25/vector search for markdown | When index.md exceeds comfortable context-window size (~100+ sources) |
| **Dataview** | Query frontmatter inside Obsidian | When you want dashboards (tags, source counts, stale pages) |
| **Mermaid** | Diagrams and flowcharts inside markdown | For visualizing processes, architectures, or relationships |
| **Git** | Version control | From day one (recommended) |

> **Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase.**

---

## Rules

- **NEVER write to `raw/`**. It is immutable.
- **Always use frontmatter** on new wiki pages.
- **Always cross-link** with `[[wiki-link]]` syntax — when creating/updating a page, always read `wiki/index.md` first and link to relevant existing pages in both `related:` frontmatter and body text.
- **Always log** every ingest, query-filing, and lint pass.
- Prefer `edit` over `write` when updating existing pages.
- **Cross-linking is easily skipped** — when creating/updating a page, always `read` `wiki/index.md` first and add `[[wiki-link]]` citations to relevant existing pages. Treat it as mandatory, not optional.
- **Co-evolve the schema:** As you discover what works, update `OPENCODE.md` with new conventions, page types, and workflows.
- **Execute autonomously:** Do not ask the user for permission before writing wiki pages, filing query answers, or committing when `auto_commit: true` is set in `.wiki/config.json`.

(End of file)
