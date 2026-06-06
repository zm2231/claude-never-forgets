# claude-never-forgets

**Claude Code forgets everything when you close the terminal. This fixes that.**

Every conversation you have with Claude Code is full of decisions, debugging context, and the architectural reasoning that got you to a working answer. Close the session and it's gone. The next one starts from zero, and you spend the first ten minutes re-explaining what you already explained yesterday.

`claude-never-forgets` gives Claude Code a memory that gets sharper every session:

- **Auto-exports** every session to searchable markdown when you close the terminal
- **Indexes** everything with [QMD](https://github.com/tobi/qmd): keyword, semantic, and hybrid search
- **`/recall`** lets Claude load context from any past session before it starts new work
- **One-command setup** that works across all your projects

---

## What this fork adds: Codex sessions too

Upstream remembers Claude Code. This fork also remembers [Codex](https://developers.openai.com/codex/).

If you run both agents, your memory shouldn't be split across two silos. `codex-export.py` reads Codex's on-disk rollouts and writes them into the **same** QMD vault, in the same markdown shape, with `agent: codex` in the frontmatter so you can still tell them apart. One `/recall` now searches across both.

It walks `$CODEX_HOME/sessions/**/rollout-*.jsonl` recursively, handles the older and current rollout schemas, and dedupes by mtime so a re-run only rewrites sessions that actually changed. Codex has no clean "session ended" signal the way Claude Code does, so the wiring is a periodic backfill on cron or launchd rather than a per-turn hook. Full setup lives in [`setup-memory/scripts/CODEX.md`](setup-memory/scripts/CODEX.md).

```bash
cp setup-memory/scripts/codex-export.py ~/.codex/hooks/
python3 ~/.codex/hooks/codex-export.py --backfill   # defaults to $CODEX_HOME/sessions
qmd update && qmd embed
```

---

## Install

```bash
# 1. Clone this repo
git clone https://github.com/menkesu/claude-never-forgets.git

# 2. Copy the skill into your project
cp -r claude-never-forgets/setup-memory your-project/.claude/skills/

# 3. Open Claude Code in your project and say:
/setup-memory
```

That's it. Claude reads the skill, runs the setup, and wires everything up.

---

## What happens after setup

Every time you close a Claude Code session:
1. A `SessionEnd` hook fires automatically
2. Your session is exported from raw JSONL to clean markdown
3. QMD re-indexes your vault in the background

Next time you open Claude Code:
```
> /recall what did we decide about the auth system

Searching vault... found 3 relevant sessions.

Session 2026-03-15: You decided to use JWT with refresh tokens
instead of session cookies because...
```

No more starting from zero.

---

## How `/recall` works

### Temporal: "what did I do yesterday?"
```
/recall yesterday
/recall last week
/recall 2026-03-15
```
Searches session files by date. Shows what you worked on and when.

### Topic: "what do we know about X?"
```
/recall authentication system
/recall database migration issues
/recall that bug with the API timeout
```
Hybrid search across all your sessions, decisions, and docs. Finds the right context even when you don't remember the exact words you used.

### Files: "sessions that touched X"
```
/recall sessions that modified auth middleware
```
Finds every session where specific files were edited.

---

## How it works under the hood

```
~/.claude/vault/                    ← Your searchable knowledge base
├── sessions/                       ← Auto-exported conversations (Claude + Codex)
│   ├── 2026-03-15_a1b2c3d4.md
│   ├── 2026-03-16_e5f6g7h8.md
│   └── ...
├── decisions/                      ← Key architectural decisions (you create these)
├── project-docs/                   ← Your project documentation
└── patterns/                       ← Reusable code patterns

~/.claude/hooks/                    ← Automation
├── session-export.py               ← Claude Code JSONL → clean markdown
└── session-end.sh                  ← Fires on every Claude session close

~/.codex/hooks/                     ← Codex automation (this fork)
└── codex-export.py                 ← Codex rollouts → the same markdown vault
```

**Session export** parses each session file, pulls out user messages and assistant responses (no tool calls, no thinking blocks), and writes clean markdown with YAML frontmatter: session ID, date, git branch, files touched, and topic summaries.

**QMD** gives you three search modes:
- `qmd search "topic"`: BM25 keyword search (instant)
- `qmd vsearch "concept"`: semantic search by meaning (finds related content with no exact-word match)
- `qmd query "question"`: hybrid with reranking (best quality, ~2s)

**The SessionEnd hook** runs in under 500ms. QMD re-indexing happens in the background and never blocks your terminal.

---

## Prerequisites

- [Node.js](https://nodejs.org/) (for installing QMD via npm)
- [Python 3](https://www.python.org/) (for the session export scripts)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI

QMD and its embedding models (~330MB on first run) get installed automatically by the setup script.

---

## Manual setup

If you'd rather wire it up yourself instead of using `/setup-memory`:

```bash
# Install QMD
npm install -g @tobilu/qmd

# Create vault
mkdir -p ~/.claude/vault/{sessions,decisions,project-docs,patterns}
mkdir -p ~/.claude/hooks

# Install scripts
cp setup-memory/scripts/session-export.py ~/.claude/hooks/
cp setup-memory/scripts/session-end.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/session-end.sh

# Configure QMD collections
qmd collection add ~/.claude/vault/sessions --name sessions
qmd collection add ~/.claude/vault/decisions --name decisions
qmd collection add ~/.claude/vault/project-docs --name project-docs
qmd collection add ~/.claude/vault/patterns --name patterns

# Backfill existing sessions
python3 ~/.claude/hooks/session-export.py --backfill ~/.claude/projects/<your-project>/

# Index and embed
qmd update && qmd embed

# Install /recall skill
cp -r setup-memory/assets/recall-skill .claude/skills/recall
```

Then add the SessionEnd hook to your `.claude/settings.json` (project or global):

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/session-end.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

To pull in Codex sessions too, see [`setup-memory/scripts/CODEX.md`](setup-memory/scripts/CODEX.md).

---

## Seeding your vault

Once setup is done, you can add decision docs and patterns to make the vault richer:

```bash
cat > ~/.claude/vault/decisions/auth-system.md << 'EOF'
---
date: 2026-03
status: completed
---
# Auth System Decision
Chose JWT with refresh tokens over session cookies.
Key tradeoff: stateless scaling vs. token revocation complexity.
## Key files
- src/middleware/auth.ts
- src/lib/jwt.ts
EOF
```

The more context in your vault, the smarter `/recall` gets.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `qmd: command not found` | Add npm global bin to PATH: `export PATH="$PATH:$(npm bin -g)"` |
| Embedding fails | First `qmd embed` downloads a ~330MB model. Needs internet. |
| Hook doesn't fire | Verify `SessionEnd` is inside the `"hooks"` key in settings.json |
| 0 files indexed | Run `qmd update` after adding files |
| Symlinks show 0 files | QMD doesn't follow symlinks. Copy files instead. |
| Codex sessions missing | Run the backfill in [CODEX.md](setup-memory/scripts/CODEX.md); check `$CODEX_HOME` |

---

## Credits

This project stands on the shoulders of:

- **[Artem Zhutov](https://x.com/artemxtech/status/2028330693659332615)**: his ["Grep Is Dead"](https://x.com/artemxtech/status/2028330693659332615) article and [personal-os-skills/recall](https://github.com/ArtemXTech/personal-os-skills/tree/main/skills/recall) skill inspired this implementation. Artem's insight: grep matches strings, but QMD ranks by relevance, and that changes everything for AI context recall.

- **[QMD](https://github.com/tobi/qmd)** by [Tobias Lutke](https://x.com/tobi): the local search engine that powers the whole system. BM25 + semantic + hybrid search over markdown files, all running locally on your machine.

---

## Built by

**[Udi Menkes](https://www.linkedin.com/in/udimenkes/)**: AI Product Leader building Financial Language Models and AI-native products at Intuit. Also building [GenAI PM](https://genaipm.com), daily and weekly AI product management briefs for 5,000+ builders.

Codex connector added in this fork by [Zain Merchant](https://github.com/zm2231).

---

## License

MIT. Use it, fork it, improve it.
