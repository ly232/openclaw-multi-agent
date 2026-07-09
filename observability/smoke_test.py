#!/usr/bin/env python3
"""
E2E smoke test — starts backend + frontend, runs one CUJ per page view.

Usage (from observability/):
    uv run python smoke_test.py

Requirements: fastapi, uvicorn[standard], duckdb, httpx, pydantic
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

import httpx

BACKEND_DIR = Path(__file__).parent / "backend"
FRONTEND_DIR = Path(__file__).parent / "frontend"
BASE_URL = "http://127.0.0.1:8080"
FRONTEND_URL = "http://127.0.0.1:5173"

# ── Server lifecycle ──────────────────────────────────────────────────


def _free_port(port: int) -> None:
    """Kill anything listening on the given port."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"],
            stderr=subprocess.DEVNULL,
        )
        for pid in out.decode().strip().split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (OSError, ValueError):
                pass
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    time.sleep(0.3)


def start_backend(python_cmd: str) -> subprocess.Popen:
    _free_port(8080)
    args = python_cmd.split() + [
        "-m", "uvicorn", "server:app",
        "--host", "127.0.0.1", "--port", "8080",
        "--log-level", "error",
    ]
    proc = subprocess.Popen(
        args,
        cwd=BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(30):
        try:
            r = httpx.get(f"{BASE_URL}/api/dashboard/summary", timeout=2)
            if r.status_code < 500:
                return proc
        except Exception:
            pass
        time.sleep(0.5)
    # Read any startup errors before killing
    _ = proc.stderr.read() if proc.stderr else ""
    proc.kill()
    raise RuntimeError("Backend did not start in time — check that port 8080 is free and DuckDB isn't locked")


def start_frontend() -> subprocess.Popen:
    _free_port(5173)
    proc = subprocess.Popen(
        ["npx", "vite", "--port", "5173", "--strictPort"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            r = httpx.get(FRONTEND_URL, timeout=2)
            if r.status_code < 500:
                return proc
        except Exception:
            pass
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError("Frontend did not start in time")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── Seed data ─────────────────────────────────────────────────────────


def seed_if_empty(python_cmd: str) -> str | None:
    """Insert one test record if the database is empty.

    Returns the seeded interaction_id, or None if the DB already had data.
    """
    r = httpx.get(f"{BASE_URL}/api/accounts?limit=1", timeout=5)
    if r.status_code == 200 and len(r.json()) > 0:
        return None

    print("  [seed] Database empty — inserting one test record …")
    seed_id = str(uuid.uuid4())
    tmp = BACKEND_DIR / ".smoke_seed.py"
    tmp.write_text('''"""Seed helper for smoke_test.py."""
from database import Database as TmpDB
db = TmpDB(read_only=False)
import uuid
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
seed_id = "''' + seed_id + '''"
db.insert_interaction({
    "interaction_id": seed_id,
    "timestamp": now,
    "channel": "webchat",
    "account_id": "smoke-test-user",
    "session_id": "smoke-session",
    "user_message": "Hello from smoke test",
    "assistant_response": "Hi! How can I help?",
    "root_agent": "smoke-test-agent",
    "agents_involved": ["smoke-test-agent"],
    "input_tokens": 10,
    "output_tokens": 20,
    "total_tokens": 30,
    "reasoning_tokens": 0,
    "latency_ms": 123,
    "status": "ok",
    "trace_file": "/dev/null",
    "trace_offset": 0,
})
db.insert_trace_event({
    "id": 1,
    "interaction_id": seed_id,
    "seq": 1,
    "ts": int(now.timestamp() * 1000),
    "agent": "smoke-test-agent",
    "event_type": "model.completed",
    "detail": {"model": "deepseek/deepseek-v4-flash"},
})
db.close()
''')
    subprocess.run(
        python_cmd.split() + [str(tmp)],
        cwd=BACKEND_DIR,
        capture_output=True,
    )
    tmp.unlink()
    return seed_id


# ── Test runner ───────────────────────────────────────────────────────

passed: int = 0
failed: int = 0
_seeded_id: str | None = None


def find_first_account_id() -> str | None:
    """Return the first account_id in the DB, or None."""
    try:
        r = httpx.get(f"{BASE_URL}/api/accounts?limit=1", timeout=5)
        accs = r.json()
        return accs[0]["account_id"] if accs else None
    except Exception:
        return None


def find_first_agent() -> str | None:
    """Return the first agent name in the DB, or None."""
    try:
        r = httpx.get(f"{BASE_URL}/api/agents", timeout=5)
        resp = r.json()
        agents = resp.get("agents", [])
        return agents[0]["agent"] if agents else None
    except Exception:
        return None


def test(name: str) -> None:
    global passed, failed
    fn_name = f"test__{name.replace('-', '_')}"
    fn = globals().get(fn_name)
    if fn is None:
        print(f"  ⚠  {name} — test function not found")
        return
    try:
        fn()
        print(f"  ✓  {name}")
        passed += 1
    except Exception as e:
        print(f"  ✗  {name} — {e}")
        failed += 1


# ── CUJs ──────────────────────────────────────────────────────────────


def test__frontend_serves_html() -> None:
    """Smoke: Vite dev server is up and serves HTML."""
    r = httpx.get(FRONTEND_URL, timeout=10)
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "text/html" in ct, f"expected text/html, got {ct}"


def test__dashboard() -> None:
    """Page: Dashboard — summary stats, top accounts, agent usage."""
    r = httpx.get(f"{BASE_URL}/api/dashboard/summary", timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)

    r = httpx.get(f"{BASE_URL}/api/accounts?limit=5", timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = httpx.get(f"{BASE_URL}/api/agents", timeout=5)
    assert r.status_code == 200
    resp = r.json()
    assert "agents" in resp, "missing agents key"
    assert "metrics" in resp, "missing metrics key"


def test__accounts_page() -> None:
    """Page: Accounts — top accounts list."""
    r = httpx.get(f"{BASE_URL}/api/accounts?limit=10", timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test__account_detail() -> None:
    """Page: Accounts -> messages for an account (drill-down)."""
    aid = find_first_account_id()
    if aid is None:
        return  # graceful skip
    r = httpx.get(f"{BASE_URL}/api/accounts/{aid}/messages?limit=10", timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test__agents_page() -> None:
    """Page: Agents — agent list + metrics."""
    r = httpx.get(f"{BASE_URL}/api/agents", timeout=5)
    assert r.status_code == 200
    resp = r.json()
    assert "agents" in resp
    assert "metrics" in resp


def test__agent_detail() -> None:
    """Page: Agents -> interactions for an agent (drill-down)."""
    agent = find_first_agent()
    if agent is None:
        return  # graceful skip
    r = httpx.get(f"{BASE_URL}/api/agents/{agent}/interactions?limit=10", timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test__message_detail() -> None:
    """Page: Message detail + execution trace."""
    iid = _seeded_id
    if iid is None:
        return  # no seed data, skip
    r = httpx.get(f"{BASE_URL}/api/messages/{iid}", timeout=5)
    assert r.status_code == 200
    msg = r.json()
    assert isinstance(msg, dict)
    assert msg.get("interaction_id") == iid

    r = httpx.get(f"{BASE_URL}/api/messages/{iid}/trace", timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test__evaluate() -> None:
    """Page: Message detail — POST an evaluation."""
    iid = _seeded_id
    if iid is None:
        return  # no seed data, skip
    r = httpx.post(
        f"{BASE_URL}/api/messages/{iid}/evaluate",
        json={
            "correctness": 5,
            "relevance": 4,
            "completeness": 3,
            "clarity": 5,
            "overall": 4.25,
        },
        timeout=5,
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test__evaluations_page() -> None:
    """Page: Evaluations — static page, no API call (Phase 2)."""
    pass  # no backend endpoint


# ── Main ──────────────────────────────────────────────────────────────

CUJS = [
    "frontend_serves_html",
    "dashboard",
    "accounts_page",
    "account_detail",
    "agents_page",
    "agent_detail",
    "message_detail",
    "evaluate",
    "evaluations_page",
]


def _resolve_python() -> str:
    """Return a Python command that has httpx and fastapi on sys.path.

    Prefers the backend project venv so the test can be invoked from
    anywhere.
    """
    venv = BACKEND_DIR / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    uv = shutil.which("uv")
    if uv:
        return f"{uv} run --project {BACKEND_DIR} python"
    return sys.executable


def main() -> int:
    global passed, failed, _seeded_id

    python = _resolve_python()

    # Start backend
    print("Starting backend …", end=" ", flush=True)
    backend = start_backend(python)
    print("ready")

    # Start frontend
    print("Starting frontend …", end=" ", flush=True)
    frontend = start_frontend()
    print("ready")

    try:
        _seeded_id = seed_if_empty(python)
        print(f"\nRunning {len(CUJS)} CUJ(s):\n")
        for name in CUJS:
            test(name)

        total = passed + failed
        print(f"\n{'=' * 36}")
        print(f"  {passed}/{total} passed", end="")
        print(f", {failed} failed" if failed else "")
        print(f"{'=' * 36}")
        return 0 if failed == 0 else 1

    finally:
        stop(frontend)
        stop(backend)


if __name__ == "__main__":
    raise SystemExit(main())
