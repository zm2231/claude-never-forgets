---
name: recall
description: >
  Search and load context from past coding sessions (Claude Code and Codex),
  decisions, and project knowledge using QMD over the shared vault at
  ~/.claude/vault/. Use when the user says "recall", "what did we do",
  "what was I working on", "remind me about", "find that session where",
  or when starting a complex task that likely has prior history.
---

# Recall - Memory Search

Search `~/.claude/vault/` via QMD for prior sessions, decisions, and patterns.
The vault is shared: it holds both Claude Code and Codex sessions in one set of
collections. Codex sessions carry an `agent: codex` line in their frontmatter;
Claude Code sessions have no `agent` field. You can use that to surface
Codex-originated sessions, but it's a best-effort keyword match over the text,
not a strict field filter (QMD indexes frontmatter as plain text).

## Collections

- **sessions** — Exported Claude Code and Codex conversations
- **decisions** — Key architectural/product decisions
- **project-docs** — Product briefs, architecture, design system
- **patterns** — Reusable code patterns and conventions

## Modes

### Temporal ("yesterday", "last week")

Search sessions by date:

```bash
qmd search "2026-03-19" -c sessions -n 10
```

For a date range, use multi-get with glob:

```bash
qmd multi-get "sessions/2026-03-1*.md"
```

### Topic ("what do we know about X")

Hybrid search across all collections (best quality):

```bash
qmd query "<topic>" -n 5
```

Keyword only (faster, no reranker):

```bash
qmd search "<topic>" -n 5
```

Semantic (when exact words are unknown):

```bash
qmd vsearch "<concept>" -n 5
```

Search a specific collection:

```bash
qmd search "<topic>" -c decisions -n 5
```

### Files ("sessions that touched X")

```bash
qmd search "files_touched.*<filename>" -c sessions -n 10
```

### Surfacing Codex sessions (best-effort)

Codex sessions carry `agent: codex` in their frontmatter, so a keyword search
biases results toward them (QMD treats this as the terms `agent` and `codex`,
not a YAML field predicate, so it's a nudge, not a hard filter):

```bash
qmd search "agent codex" -c sessions -n 10
```

There is no positive marker for Claude Code sessions, so they can't be filtered
the same way; just search by topic/date and read the `agent` field (if present)
in the results.

## Workflow

1. Determine the recall mode from the user's request.
2. Run the appropriate `qmd` command(s) in the shell.
3. Open the top 2-3 result files to read their full content.
4. Synthesize and present the relevant context.
5. Ask if the user wants to dig deeper.

## Tips

- `qmd search` is instant. Use it for quick lookups.
- `qmd query` uses a reranker model. Best quality but slower (~2s).
- `qmd vsearch` finds meaning even without exact keywords.
- Session files live in `~/.claude/vault/sessions/`. Codex sessions are named `{date}_{session_id}.md` (full id); Claude Code sessions use `{date}_{id8}.md` (first 8 chars of the id).
- Frontmatter always includes `session_id`, `date`, `branch`. `files_touched` and `topics` appear only when present. Codex sessions also carry `agent: codex` and `slug`; Claude Code sessions have no `agent` field.
- Use `qmd status` to check vault health and document counts.
