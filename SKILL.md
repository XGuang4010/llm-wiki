---
name: llm-wiki
description: Karpathy-style LLM Wiki pattern for OpenCode. Ingest raw sources into a structured, interlinked markdown wiki, and file query answers back into the knowledge base.
trigger: /wiki
---

> **Before executing any workflow below, you MUST first read `RULES.md` in this skill directory.**

# LLM Wiki Skill

> **First Principle:** The wiki is a **persistent, compounding artifact**. Every ingest and every filed query makes it richer. Cross-references are pre-built. Contradictions are pre-flagged. The knowledge is compiled once and kept current — not re-derived on every query.

This skill implements the three-layer LLM Wiki architecture (raw / wiki / schema) inside OpenCode.

## Quick Reference

| Command | Action |
|---------|--------|
| `/wiki ingest <path>` or `ingest <topic>` | Search web → save to `raw/` → compile into wiki |
| `/wiki query "<question>"` | Search wiki and synthesize an answer (auto-saved to wiki) |
| `/wiki lint` | Health-check the wiki for contradictions, orphans, gaps |
| `/wiki sync` | Scan `.learning` dirs → stage new/changed files → auto-ingest into wiki |

---

## Ingest Workflow

**Trigger:** User provides a specific path/URL, OR asks to "搜集/查找/研究 [topic] 相关的资料/知识/方法/解决方案" without providing a path.

**Source acquisition — two cases:**

> **Case A — Specific path or URL given:** `read` that file/URL directly and proceed to Step 2.
>
> **Case B — No path given (搜集/查找/研究/调查/寻找…):** The user wants you to find relevant information on the web. You must:
> 1. Use `websearch` or `webfetch` to gather content from the internet
> 2. Save the raw content to `raw/articles/YYYY-MM-DD-topic.md` with the raw-source frontmatter
> 3. `read` the saved file
> 4. Then proceed to Step 2

**A single source typically touches 5-15 wiki pages.** Do not stop at creating just the summary page.

**Steps:**
1. **Acquire source** (follow Case A or B above).
2. `read` `wiki/index.md` to understand current structure.
   - If wiki is empty (first ingest): skip contradiction check, proceed to Step 5
   - If wiki has content: `read` relevant existing concept/entity pages to identify contradictions
3. **Check for contradictions (only if wiki has existing content):** Compare the new source against existing wiki claims (dates, numbers, definitions, rankings). Flag any conflicts to the user *before* writing updates. Skip this step on first ingest.
4. Discuss key takeaways with the user.
5. Create/update a **summary page** in `wiki/sources/YYYY-MM-DD-slug.md`.
6. Create/update **concept pages** in `wiki/concepts/` (extracted terms, techniques, frameworks). A single source often creates 3-6 concept pages.
7. Create/update **entity pages** in `wiki/entities/` (people, organizations, tools, CVEs, malware families).
8. **Add cross-links in the new/updated pages:** `read` `wiki/index.md` to know what pages already exist. For each new or updated page, add `[[wiki-link]]` links to relevant *existing* pages — both in the `related:` frontmatter field and in the body text. This builds the link graph as pages are created.
9. Update `wiki/index.md` with new/updated entries (follow the index format below).
10. Update `wiki/overview.md` if the domain synthesis has shifted.
11. Append to `wiki/log.md` using the format below.
12. Offer to run `git add . && git commit -m "ingest: <title>"`.

**Frontmatter template for wiki pages:**
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

**Frontmatter template for raw sources (saved before ingest):**
```yaml
---
title: Source Title
type: raw-source
source: web_search | url | file
tags: [topic1, topic2]
created: YYYY-MM-DD
summary: One-line description of the source
---
```

**index.md format:**
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

## Query & File Workflow

**Trigger:** user asks any question against the wiki.

**Every query answer is automatically saved to `wiki/queries/`.** Do not ask "file it" — just do it.

**Steps:**
1. `read` `wiki/index.md`.
2. `grep` or `read` relevant wiki pages (and raw sources if needed).
3. Synthesize an answer with `[[wiki-link]]` citations.
4. The answer can take different forms:
   - A markdown page
   - A comparison table
   - A Mermaid or flowchart diagram
   - A chart or diagram
5. **Save the answer** to `wiki/queries/YYYY-MM-DD-slug.md` (or `wiki/comparisons/` for tables). Always do this — do not ask.
6. Add frontmatter: `type: query-answer` or `type: comparison`, `question: "..."`, `sources: [...]`.
7. Add `[[wiki-link]]` citations to relevant existing pages in `related:` frontmatter and body.
8. Update `wiki/index.md` and `wiki/log.md`.

---

## Lint Workflow

**Trigger:** user says "lint wiki" or `/wiki lint`

**Steps:**
1. `grep` for contradictions (e.g., conflicting dates, numbers, claims).
2. `grep` for orphan pages (pages never linked by `[[...]]`).
3. `grep` for frequently mentioned terms lacking a concept page.
4. Check for stale claims superseded by newer sources.
5. Check `wiki/log.md` for recurring issues.
6. Suggest new questions to investigate and new sources to look for.
7. Present a markdown report to the user.
8. Append the report to `wiki/log.md`.

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
- **Cross-linking is easily skipped** — when creating/updating a page, always `read` `wiki/index.md` first and add `[[wiki-link]]` citations to relevant existing pages. Treat step 8 as mandatory, not optional.
- **Co-evolve the schema:** As you discover what works, update `OPENCODE.md` with new conventions, page types, and workflows.
