"""Log collector daemon: watches OpenClaw trajectory files, ingests into DuckDB."""

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
            if event.get("type") != "model.completed":
                pos = f.tell()
                continue
            data = event.get("data", {})
            usage = data.get("usage", {})
            msgs = data.get("messagesSnapshot", [])

            # Extract channel and account from sessionKey
            session_key = event.get("sessionKey", "")
            channel = "unknown"
            account_id = "unknown"
            if session_key:
                parts = session_key.split(":")
                if len(parts) >= 2:
                    channel = parts[1] if parts[1] != "main" else "webchat"
                if len(parts) >= 4:
                    account_id = parts[3]

            user_msg = ""
            asst_msg = ""
            for m in msgs:
                role = m.get("role", "")
                c = m.get("content", "")
                txt = ""
                if isinstance(c, str):
                    txt = c
                elif isinstance(c, list):
                    for block in c:
                        if block.get("type") == "text":
                            txt = block.get("text", "")
                            break
                if role == "user":
                    user_msg = _strip_conversation_info(txt[:1000])
                elif role == "assistant" and not asst_msg:
                    asst_msg = txt[:1000]

            asst_texts = data.get("assistantTexts", [])
            interaction = {
                "interaction_id": str(uuid.uuid4()),
                "timestamp": _parse_ts(event.get("ts", 0)),
                "channel": channel,
                "account_id": account_id,
                "session_id": session_id,
                "user_message": user_msg or "",
                "assistant_response": asst_texts[0] if asst_texts else asst_msg,
                "root_agent": event.get("source", "unknown"),
                "agents_involved": [event.get("source", "unknown")],
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
    return db.conn.execute("SELECT changes()").fetchone()[0]


def run_loop() -> None:
    db = get_db()
    print(f"[collector] Started. Polling every {POLL_INTERVAL}s...")
    while True:
        n = collect_once(db)
        pruned = prune_old_data(db)
        if pruned:
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
        pruned = prune_old_data(db)
        if pruned:
            print(f"[collector] Pruned {pruned} old interaction(s)")
        print(f"Ingested {n} interaction(s)")
    elif len(sys.argv) > 1 and sys.argv[1] == "--reset":
        pass  # already handled above
    else:
        run_loop()


if __name__ == "__main__":
    main()
