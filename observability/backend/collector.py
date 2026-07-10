"""Log collector — runs as a daemon thread inside the server process.

Reads OpenClaw trajectory files (*.trajectory.jsonl) and ingests parsed
interactions into DuckDB via the shared `get_db()` singleton.

No file locks are acquired since it shares the same process / DuckDB
connection as the HTTP server.
"""

import json
import os
import uuid
import glob
from pathlib import Path
from datetime import datetime, timezone
from database import get_db


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
    peer = parts[2] if len(parts) >= 3 else ""
    if peer and not peer.startswith("tui-"):
        channel = peer
    else:
        channel = "webchat" if agent_id == "main" else agent_id
    account_id = parts[3] if len(parts) >= 4 else "unknown"
    return agent_id, channel, account_id


def parse_trajectory(filepath: str, state: dict) -> int:
    """Parse a trajectory file and insert interactions into the shared DB.

    Returns the number of interactions ingested.
    """
    db = get_db()
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

            agent, channel, account_id = _parse_session_key(event.get("sessionKey", ""))

            user_msg = pending_prompt_user_msg or _extract_user_msg(msgs)
            pending_prompt_user_msg = ""

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


def collect_once() -> int:
    """Run one collection pass. Returns number of interactions ingested."""
    db = get_db()
    state = load_state()
    total = 0
    for fp in sorted(glob.glob(TRAJECTORY_GLOB)):
        try:
            n = parse_trajectory(fp, state)
            total += n
        except Exception as e:
            print(f"Error processing {fp}: {e}")
    save_state(state)

    pruned = db.prune_old_data()
    if pruned:
        print(f"[collector] Pruned {pruned} old interaction(s)")

    if total:
        print(f"[collector] Ingested {total} interactions at {datetime.now().isoformat()}")
    return total
