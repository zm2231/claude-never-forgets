# Codex sessions → same vault

`codex-export.py` is the Codex sibling of `session-export.py`. It reads Codex CLI
rollouts and writes the **same** markdown shape into the **same** vault
(`~/.claude/vault/sessions/`), so QMD indexes Claude Code and Codex sessions
together. Frontmatter carries `agent: codex` so the two are distinguishable.

## What it reads

`$CODEX_HOME/sessions/**/rollout-*.jsonl` (default `~/.codex/sessions`), nested
by date. Three on-disk schemas are handled:

- legacy untyped header (`{"id","timestamp","git"}` first line)
- legacy flat records (`{"type":"message",...}`)
- current wrapped records (`{"type":"response_item","payload":{...}}`)

User/assistant text is taken from `response_item` messages. When a rollout has
**no** `response_item` messages (e.g. some `codex exec` / review-mode sessions),
it falls back to `event_msg` `user_message` / `agent_message`. Reasoning and tool
calls are dropped (parity with the Claude exporter). `files_touched` is mined
from `apply_patch` / tool-call arguments and made relative to the session `cwd`.

Dedup is **mtime-based**: a session is re-exported only when its rollout is newer
than the existing `.md`, so backfill is cheap to re-run.

## Wiring — backfill (cron / launchd)

Codex has no Claude-style `SessionEnd` event. Its `Stop` hook is turn-scoped (it
fires after every turn, not once at session close) and matching hooks can run
concurrently, so driving export+embed from `Stop` would re-index repeatedly
during a single session. Periodic backfill is the right model: export changed
sessions and index once per interval.

```bash
cp setup-memory/scripts/codex-export.py ~/.codex/hooks/
python3 ~/.codex/hooks/codex-export.py --backfill   # defaults to $CODEX_HOME/sessions
qmd update && qmd embed
```

launchd example (every 10 min): run the two commands above from a
`StartInterval = 600` agent. mtime dedup means each run only rewrites the
sessions that actually changed.
