#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

VAULT_DIR = Path.home() / ".claude" / "vault" / "sessions"
CODEX_SESSIONS = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"
MAX_BLOCKS = 200
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_TEXT_LEN = 2000

_PATCH_FILE = re.compile(r"\*\*\* (?:Add|Update|Delete) File: (.+)")


def normalize(obj):
    t = obj.get("type")
    if t == "response_item":
        payload = obj.get("payload") or {}
        return payload.get("type"), payload
    if t == "session_meta":
        return "session_meta", obj.get("payload") or {}
    if t == "event_msg":
        return "event_msg", obj.get("payload") or {}
    if t in ("message", "reasoning", "function_call", "function_call_output"):
        return t, obj
    if t is None and "id" in obj and "timestamp" in obj:
        return "session_meta", obj
    return None, {}


def message_text(payload):
    content = payload.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in ("input_text", "output_text", "text"):
            parts.append(str(block.get("text", "")))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(p for p in parts if p).strip()


def extract_file_paths(payload):
    paths = set()
    raw = payload.get("arguments")
    if not isinstance(raw, str):
        return paths
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        args = None
    if isinstance(args, dict):
        for key in ("file_path", "path", "filePath"):
            val = args.get(key)
            if isinstance(val, str):
                paths.add(val)
        patch = args.get("input") or args.get("patch")
        if isinstance(patch, str):
            paths.update(m.strip() for m in _PATCH_FILE.findall(patch))
    elif args is None:
        paths.update(m.strip() for m in _PATCH_FILE.findall(raw))
    return {p for p in paths if p}


def export_session(jsonl_path):
    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        return None

    metadata = {}
    raw_files = set()
    item_messages = []
    event_messages = []
    large_file = jsonl_path.stat().st_size > MAX_FILE_SIZE

    def add(bucket, role, text):
        if large_file and len(bucket) >= MAX_BLOCKS:
            return
        bucket.append((role, text))

    with open(jsonl_path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind, payload = normalize(obj)

            if kind == "session_meta" and not metadata:
                git = payload.get("git") or {}
                metadata = {
                    "session_id": payload.get("id", jsonl_path.stem),
                    "branch": git.get("branch", "unknown"),
                    "slug": payload.get("originator", ""),
                    "cwd": payload.get("cwd", ""),
                }
                continue

            if kind == "message":
                add(item_messages, payload.get("role"), message_text(payload))
            elif kind == "event_msg":
                etype = payload.get("type")
                if etype == "user_message":
                    add(event_messages, "user", str(payload.get("message", "")).strip())
                elif etype == "agent_message":
                    add(event_messages, "assistant", str(payload.get("message", "")).strip())
            elif kind == "function_call":
                raw_files.update(extract_file_paths(payload))

    source = item_messages if item_messages else event_messages
    truncated = large_file and len(source) >= MAX_BLOCKS

    messages = []
    for role, text in source:
        if role == "user":
            if text and not text.startswith("<"):
                messages.append(("user", text))
        elif role == "assistant":
            if text:
                if len(text) > MAX_TEXT_LEN:
                    text = text[:MAX_TEXT_LEN] + "\n\n[truncated]"
                messages.append(("assistant", text))
    if truncated:
        messages.append(("system", f"[Session truncated at {MAX_BLOCKS} blocks due to size]"))

    user_count = sum(1 for role, _ in messages if role == "user")
    if user_count < 2:
        return None

    session_id = metadata.get("session_id", jsonl_path.stem)
    mtime = jsonl_path.stat().st_mtime
    date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    output_path = VAULT_DIR / f"{date_str}_{session_id}.md"
    if output_path.exists() and output_path.stat().st_mtime >= mtime:
        return None

    cwd = metadata.get("cwd", "")
    files_touched = set()
    for p in raw_files:
        if cwd and p.startswith(cwd + "/"):
            p = p[len(cwd) + 1:]
        files_touched.add(p)

    topics = []
    for role, text in messages:
        if role == "user" and len(topics) < 3:
            topic = text[:100].replace("\n", " ").strip()
            if topic:
                topics.append(topic)

    short_id = session_id[:8]
    fm_lines = [
        "---",
        f"session_id: {session_id}",
        f"date: {date_str}",
        f"branch: {metadata.get('branch', 'unknown')}",
        f"slug: {metadata.get('slug', '')}",
        "agent: codex",
    ]
    if files_touched:
        fm_lines.append("files_touched:")
        for fp in sorted(files_touched)[:20]:
            fm_lines.append(f"  - {fp}")
    if topics:
        fm_lines.append("topics:")
        for t in topics:
            fm_lines.append(f'  - "{t}"')
    fm_lines.append("---")

    body_lines = [f"\n# Session: {date_str} ({short_id}) [codex]\n"]
    for role, text in messages:
        if role == "user":
            body_lines.append(f"## User\n{text}\n")
        elif role == "assistant":
            body_lines.append(f"## Assistant\n{text}\n")
        elif role == "system":
            body_lines.append(f"*{text}*\n")

    output_path.write_text("\n".join(fm_lines) + "\n" + "\n".join(body_lines))
    os.utime(output_path, (mtime, mtime))
    return output_path


def backfill(sessions_dir):
    sessions_dir = Path(sessions_dir)
    exported = 0
    skipped = 0
    for jsonl_file in sorted(sessions_dir.rglob("rollout-*.jsonl")):
        result = export_session(jsonl_file)
        if result:
            exported += 1
            print(f"  Exported: {result.name}")
        else:
            skipped += 1
    print(f"\nDone: {exported} exported, {skipped} skipped")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export Codex CLI session rollouts to the same searchable markdown vault "
            "as session-export.py (~/.claude/vault/sessions). Dedup is mtime-based: a "
            "session is re-exported only when its rollout is newer than the existing .md. "
            "Reads $CODEX_HOME/sessions/**/rollout-*.jsonl (legacy flat + response_item schemas)."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--transcript", help="Path to a single rollout JSONL file")
    group.add_argument(
        "--backfill",
        nargs="?",
        const=str(CODEX_SESSIONS),
        default=None,
        help="Codex sessions dir, recursive (omit value for $CODEX_HOME/sessions)",
    )
    args = parser.parse_args()

    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    if args.transcript:
        result = export_session(args.transcript)
        print(f"Exported: {result}" if result else "Skipped (already exported or trivial)")
    else:
        backfill(args.backfill or CODEX_SESSIONS)


if __name__ == "__main__":
    main()
