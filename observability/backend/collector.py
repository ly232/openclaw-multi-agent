"""Log collector daemon: watches OpenClaw trajectory files, ingests into DuckDB.

Example usagae:

# One-shot run:
uv run python collector.py --once

# Contineous run with logging to stdout:
uv run python collector.py

# Contineous run as a daemon process:
nohup uv run python collector.py > ~/.openclaw/observability/collector.log 2>&1 &
echo $! > ~/.openclaw/observability/collector.pid

# Stop daemon with:
kill $(cat ~/.openclaw/observability/collector.pid)

Quick note on duckdb locking:

  ┌────────────────┐      shared read lock      ┌──────────────────┐                                                                                                               
  │  Server (GET)  │ ─────────────────────────→ │  observability   │                                                                                                              
  │  (read_only)   │                            │   .duckdb        │                                                                                                              
  └────────────────┘                            │                  │                                                                                                             
                                                │  ↑ write lock    │                                                                                                              
  ┌────────────────┐     exclusive write lock   │  ↓ shared read   │                                                                                                              
  │  Collector     │  ────────────────────────→ │                  │                                                                                                             
  │  (read_write)  │                            └──────────────────┘                                                                                                            
  └────────────────┘
"""

import json, os, time, uuid, glob
from pathlib import Path
from datetime import datetime, timezone
from database import Database, get_db


def _parse_ts(ts):
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    if isinstance(ts, str):
        ts = ts.replace("Z", "+00:00").replace("z", "+00:00")
        return datetime.fromisoformat(ts)
    return datetime.now(timezone.utc)


def _strip_conversation_info(text: str) -> str:
    """Remove the 'Conversation info (untrusted metadata)' JSON prefix if present."""
    if text.startswith("Conversation info"):
        parts = text.split("\n\n", 1)
        if len(parts) > 1:
            return parts[1]
    return text


STATE_DIR = Path("~/.openclaw/observability").expanduser()
STATE_FILE = STATE_DIR / "collector_state.json"
TRAJECTORY_GLOB = str(Path("~/.openclaw/agents/*/sessions/*.trajectory.jsonl").expanduser())
POLL_INTERVAL = 30


def load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _extract_user_msg(msgs: list) -> str:
    """Extract the last user role message content from a messages list."""
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        c = m.get("content", "")
        if isinstance(c, str):
            return _strip_conversation_info(c[:1000])
        if isinstance(c, list):
            for block in c:
                if block.get("type") == "text":
                    return _strip_conversation_info(block.get("text", "")[:1000])
    return ""


def _extract_last_prompt_line(prompt: str) -> str:
    """Extract the last meaningful line from a prompt text as the user message."""
    lines = [l.rstrip() for l in prompt.split("\n") if l.strip()]
    return _strip_conversation_info(lines[-1][:1000]) if lines else ""


def _parse_session_key(session_key: str) -> tuple:
    """Parse sessionKey into (agent_id, channel, account_id).

    Format: agent:{agentId}:{channelOrPeer}:{accountId}:...
    """
    if not session_key:
        return "unknown", "unknown", "unknown"
    parts = session_key.split(":")
    agent_id = parts[1] if len(parts) >= 2 else "unknown"
    # parts[2] is the actual channel when it's a well-known name
    # (e.g. "openclaw-weixin"); if it looks like a TUI session UUID
    # (starts with "tui-") treat it as webchat.
    peer = parts[2] if len(parts) >= 3 else ""
    if peer and not peer.startswith("tui-"):
        channel = peer
    else:
        channel = "webchat" if agent_id == "main" else agent_id
    account_id = parts[3] if len(parts) >= 4 else "unknown"
    return agent_id, channel, account_id


def parse_trajectory(filepath: str, db: Database, state: dict) -> int:
    last_offset = state.get(filepath, {}).get("offset", 0)
    count = 0
    try:
        f = open(filepath, errors="replace")
    except OSError:
        return 0
    with f:
        try:
            f.seek(last_offset)
        except OSError:
            return 0
        session_id = Path(filepath).stem
        if session_id.endswith(".trajectory"):
            session_id = session_id.replace(".trajectory", "")

        # Track the latest user-submitted message from prompt.submitted events.
        # Each prompt.submitted immediately feeds a model.completed, but multiple
        # model.completed events may share the same context window (e.g. thinking
        # refinements).  We consume the tracked prompt once per model.completed.
        pending_prompt_user_msg = ""

        pos = f.tell()
        while True:
            line = f.readline()
            if not line:
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                pos = f.tell()
                continue

            event_type = event.get("type")

            # Track prompt.submitted — the raw prompt text ends with the latest
            # user input, giving us the correct per-turn user message.
            if event_type == "prompt.submitted":
                prompt = event.get("data", {}).get("prompt", "")
                if prompt:
                    pending_prompt_user_msg = _extract_last_prompt_line(prompt)
                pos = f.tell()
                continue

            if event_type != "model.completed":
                pos = f.tell()
                continue

            data = event.get("data", {})
            usage = data.get("usage", {})
            msgs = data.get("messagesSnapshot", [])

            # Extract agent, channel, account from sessionKey (not event.source)
            agent, channel, account_id = _parse_session_key(event.get("sessionKey", ""))

            # user_message: prefer the tracked prompt_submitted message, then
            # fall back to the last user role in messagesSnapshot.
            user_msg = pending_prompt_user_msg or _extract_user_msg(msgs)
            pending_prompt_user_msg = ""  # consume once

            asst_texts = data.get("assistantTexts", [])
            interaction = {
                "interaction_id": str(uuid.uuid4()),
                "timestamp": _parse_ts(event.get("ts", 0)),
                "channel": channel,
                "account_id": account_id,
                "session_id": session_id,
                "user_message": user_msg or "",
                "assistant_response": asst_texts[0] if asst_texts else "",
                "root_agent": agent,
                "agents_involved": [agent],
                "input_tokens": usage.get("input", 0),
                "output_tokens": usage.get("output", 0),
                "total_tokens": usage.get("total", 0),
                "reasoning_tokens": usage.get("reasoningTokens", 0),
                "latency_ms": 0,
                "status": "ok",
                "trace_file": filepath,
                "trace_offset": pos,
            }
            db.insert_interaction(interaction)
            count += 1
            pos = f.tell()
    state[filepath] = {"offset": pos, "mtime": os.path.getmtime(filepath)}
    return count


def collect_once(db: Database) -> int:
    state = load_state()
    total = 0
    for fp in sorted(glob.glob(TRAJECTORY_GLOB)):
        try:
            n = parse_trajectory(fp, db, state)
            total += n
        except Exception as e:
            print(f"Error processing {fp}: {e}")
    save_state(state)
    return total


def prune_old_data(db: Database, retention_days: int = 7) -> int:
    """Delete interactions older than retention_days. Returns count deleted."""
    result = db.conn.execute(
        f"DELETE FROM interactions WHERE timestamp < now() - INTERVAL '{retention_days} days'"
    )
    return result.rowcount


def run_loop() -> None:
    print(f"[collector] Started. Polling every {POLL_INTERVAL}s...")
    while True:
        db = Database(read_only=False)
        try:
            n = collect_once(db)
            pruned = prune_old_data(db)
        finally:
            db.close()
        if pruned > 0:
            print(f"[collector] Pruned {pruned} old interaction(s)")
        if n:
            print(f"[collector] Ingested {n} interactions at {datetime.now().isoformat()}")
        time.sleep(POLL_INTERVAL)


def main() -> None:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        db_path = Path("~/.openclaw/observability.duckdb").expanduser()
        if db_path.exists():
            db_path.unlink()
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("Reset: deleted database and state file")

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        db = get_db()
        n = collect_once(db)
        print(f"Ingested {n} interaction(s)")
    elif len(sys.argv) > 1 and sys.argv[1] == "--reset":
        pass  # already handled above
    else:
        run_loop()


if __name__ == "__main__":
    main()
