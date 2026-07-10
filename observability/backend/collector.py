"""Log collector — runs as a daemon thread inside the server process.

Reads OpenClaw trajectory files (*.trajectory.jsonl) and ingests parsed
interactions into DuckDB via the shared `get_db()` singleton.

Multi-agent tracking:
  Within a single trajectory file, ALL unique agents seen in model.completed
  events between prompt.submitted boundaries are included in agents_involved.

  Across trajectory files (cross-trajectory correlation), a timestamp-based
  heuristic is used: model.completed events from different agents that occur
  within a small time window are assumed to belong to the same delegation
  chain (orchestrator → coding → research).
"""

import json
import os
import uuid
import glob
from pathlib import Path
from datetime import datetime, timezone
from database import get_db

# Intra-turn agent set — populated during parse_trajectory
# Cross-trajectory timestamp index — populated during collect_once
_AGENT_TIME_INDEX: dict[int, str] = {}        # unix_ms → agent
_TIME_WINDOW_MS = 2_000                        # 2 second window for correlation


def _parse_ts(ts):
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _strip_conversation_info(text: str) -> str:
    if text.startswith("Conversation info"):
        parts = text.split("\n\n", 1)
        return parts[1] if len(parts) > 1 else text
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
    lines = [l.rstrip() for l in prompt.split("\n") if l.strip()]
    return _strip_conversation_info(lines[-1][:1000]) if lines else ""


def _parse_session_key(session_key: str) -> tuple:
    if not session_key:
        return "unknown", "unknown", "unknown"
    parts = session_key.split(":")
    agent_id = parts[1] if len(parts) >= 2 else "unknown"
    peer = parts[2] if len(parts) >= 3 else ""
    channel = peer if peer and not peer.startswith("tui-") else ("webchat" if agent_id == "main" else agent_id)
    account_id = parts[3] if len(parts) >= 4 else "unknown"
    return agent_id, channel, account_id


def _build_time_index() -> None:
    """Pre-scan all trajectories to build a timestamp → agent index.

    Enables cross-file correlation: a model.completed at time T in the
    orchestrator's trajectory that is followed by model.completed at
    time T+δ in the coding trajectory indicates delegation.
    """
    _AGENT_TIME_INDEX.clear()
    seen: set[tuple[str, str]] = set()  # (agent, timestamp) dedup
    for fp in sorted(glob.glob(TRAJECTORY_GLOB)):
        try:
            with open(fp, errors="replace") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "model.completed":
                        continue
                    sk = event.get("sessionKey", "")
                    agent, _, _ = _parse_session_key(sk)
                    ts = event.get("ts", 0)
                    if isinstance(ts, str):
                        try:
                            ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                        except (ValueError, TypeError):
                            continue
                    if not isinstance(ts, (int, float)):
                        continue
                    ts_ms = int(ts)
                    key = (agent, str(ts_ms))
                    if key in seen:
                        continue
                    seen.add(key)
                    _AGENT_TIME_INDEX[ts_ms] = agent
        except OSError:
            continue


def _find_nearby_agents(ts_ms: int, current_agent: str) -> set[str]:
    """Find agents with model.completed events within _TIME_WINDOW_MS of ts_ms."""
    nearby = set()
    if not _AGENT_TIME_INDEX:
        return nearby
    for evt_ts, agent in _AGENT_TIME_INDEX.items():
        if agent == current_agent:
            continue
        if abs(evt_ts - ts_ms) <= _TIME_WINDOW_MS:
            nearby.add(agent)
    return nearby


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
        agents_seen_in_turn: set[str] = set()

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
                agents_seen_in_turn.clear()
                pos = f.tell()
                continue

            if event_type != "model.completed":
                pos = f.tell()
                continue

            data = event.get("data", {})
            usage = data.get("usage", {})
            msgs = data.get("messagesSnapshot", [])
            event_ts = event.get("ts", 0)

            agent, channel, account_id = _parse_session_key(event.get("sessionKey", ""))

            # Track every unique agent seen since the last prompt.submitted
            agents_seen_in_turn.add(agent)

            # Cross-trajectory correlation: find other agents with events
            # close in time and include them in agents_involved.
            ts_ms = int(event_ts) if isinstance(event_ts, (int, float)) else 0
            if ts_ms:
                nearby = _find_nearby_agents(ts_ms, agent)
                for na in nearby:
                    agents_seen_in_turn.add(na)

            user_msg = pending_prompt_user_msg or _extract_user_msg(msgs)
            pending_prompt_user_msg = ""

            asst_texts = data.get("assistantTexts", [])
            interaction = {
                "interaction_id": str(uuid.uuid4()),
                "timestamp": _parse_ts(event_ts),
                "channel": channel,
                "account_id": account_id,
                "session_id": session_id,
                "user_message": user_msg or "",
                "assistant_response": asst_texts[0] if asst_texts else "",
                "root_agent": agent,
                "agents_involved": sorted(agents_seen_in_turn),
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

    # Pre-scan ALL trajectories to build the cross-file time index
    _build_time_index()

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


def backfill() -> None:
    """Full backfill: clear DB + state, re-ingest with new correlation logic."""
    print("[collector] Backfill: clearing existing data...")
    db = get_db()
    db.conn.execute("DELETE FROM evaluations")
    db.conn.execute("DELETE FROM trace_events")
    db.conn.execute("DELETE FROM interactions")
    print("[collector] Backfill: clearing collector state...")
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    _AGENT_TIME_INDEX.clear()
    print("[collector] Backfill: re-ingesting all trajectories...")
    total = collect_once()
    print(f"[collector] Backfill complete: {total} interactions ingested")


def main() -> None:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        backfill()
    else:
        print("[collector] Running in standalone loop mode...")
        import time
        while True:
            collect_once()
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
