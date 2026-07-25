"""FastAPI server for the observability dashboard.

The collector runs as a daemon thread inside the server process.  HTTP
handlers use short-lived per-request DuckDB connections to avoid TOCTOU
races on shared cursor state when multiple threads call .execute()
concurrently.  The collector uses a separate long-lived connection.
"""

import contextlib
import logging
import threading
import time
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import get_db, get_request_db, close_db, summary, top_accounts, top_agents, \
    agent_metrics, ACCOUNT_MESSAGES, AGENT_INTERACTIONS, MESSAGE_BY_ID, TRACE_EVENTS
from collector import collect_once, POLL_INTERVAL

logger = logging.getLogger(__name__)


def _collector_loop() -> None:
    """Background thread: polls trajectory files every POLL_INTERVAL seconds."""
    logger.info("Collector thread started (poll interval = %ds)", POLL_INTERVAL)
    while True:
        try:
            collect_once()
        except Exception:
            logger.exception("Collector iteration failed")
        time.sleep(POLL_INTERVAL)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    # Open the shared collector connection (crash on failure).
    get_db()
    logger.info("Database connection opened (collector)")

    # Start the collector background thread.
    t = threading.Thread(target=_collector_loop, daemon=True)
    t.start()

    yield

    logger.info("Shutting down...")
    close_db()


app = FastAPI(title="OpenClaw Observability", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def dicts(sql: str, *params):
    """Execute a read-only query on a per-request connection.

    Opens a fresh connection, runs the query, materializes results into
    Python objects, then closes.  This avoids races on shared cursor state.
    """
    db = get_request_db()
    try:
        return db.execute_dicts(sql, *params)
    except Exception:
        logger.exception("Query failed: %r params=%s", sql, params)
        return []
    finally:
        db.close()


@app.get("/api/dashboard/summary")
def dashboard_summary(days: int = Query(7, ge=1, le=31)):
    rows = dicts(summary(days), days)
    return rows[0] if rows else {}


@app.get("/api/accounts")
def list_accounts(limit: int = Query(10, ge=1, le=100), days: int = Query(7, ge=1, le=31)):
    return dicts(top_accounts(days), days, limit)


@app.get("/api/accounts/{account_id}/messages")
def account_messages(account_id: str, limit: int = Query(10, ge=1, le=100), offset: int = 0):
    return dicts(ACCOUNT_MESSAGES, account_id, limit, offset)


@app.get("/api/agents")
def list_agents(limit: int = Query(10, ge=1, le=100), days: int = Query(7, ge=1, le=31)):
    return {"agents": dicts(top_agents(days), days, limit), "metrics": dicts(agent_metrics(days), days)}


@app.get("/api/agents/{agent_id}/interactions")
def agent_interactions(agent_id: str, limit: int = Query(10, ge=1, le=100), offset: int = 0):
    return dicts(AGENT_INTERACTIONS, agent_id, limit, offset)


@app.get("/api/messages/{message_id}")
def get_message(message_id: str):
    rows = dicts(MESSAGE_BY_ID, message_id)
    return rows[0] if rows else None


@app.get("/api/messages/{message_id}/trace")
def get_trace(message_id: str):
    return dicts(TRACE_EVENTS, message_id)


class QueryRequest(BaseModel):
    sql: str


@app.post("/api/query")
def run_query(req: QueryRequest):
    """Execute arbitrary SQL and return results as columns + rows."""
    sql = req.sql.strip()
    if not sql:
        return {"columns": [], "rows": [], "error": None}
    db = get_request_db()
    try:
        cur = db.conn.execute(sql)
        cols = [cur.description[i][0] for i in range(len(cur.description))]
        raw_rows = cur.fetchall()
        # Convert to Python-native types for JSON serialization
        rows = [[_json_safe(v) for v in r] for r in raw_rows]
        return {"columns": cols, "rows": rows, "error": None}
    except Exception as e:
        logger.exception("Query failed: %s", sql)
        return {"columns": [], "rows": [], "error": str(e)}
    finally:
        db.close()


def _json_safe(v):
    """Convert DuckDB values to JSON-safe Python types."""
    import datetime
    if isinstance(v, datetime.datetime):
        return v.isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, memoryview):
        return bytes(v).hex()
    if hasattr(v, "item"):
        return v.item()
    return v


class EvalRequest(BaseModel):
    correctness: int
    relevance: int
    completeness: int
    clarity: int
    overall: float = 0.0
    evaluator_model: str = "deepseek/deepseek-v4-flash"


@app.post("/api/messages/{message_id}/evaluate")
def evaluate_message(message_id: str, req: EvalRequest):
    import uuid
    db = get_request_db()
    try:
        db.insert_evaluation({
            "evaluation_id": str(uuid.uuid4()),
            "interaction_id": message_id,
            "evaluator_model": req.evaluator_model,
            "prompt_version": "v1",
            "correctness": req.correctness,
            "relevance": req.relevance,
            "completeness": req.completeness,
            "clarity": req.clarity,
            "overall": req.overall,
        })
        return {"ok": True}
    except Exception:
        logger.exception("Evaluation insert failed")
        return {"ok": False, "error": "database error"}
    finally:
        db.close()


@app.post("/api/seed")
def seed_test_data():
    """Insert a test interaction + trace event (for smoke tests)."""
    import uuid as _uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    seed_id = str(_uuid.uuid4())
    db = get_request_db()
    try:
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
        logger.info("Seeded test interaction %s", seed_id)
        return {"interaction_id": seed_id}
    except Exception:
        logger.exception("Seed failed")
        return {"ok": False, "error": "database error"}
    finally:
        db.close()


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
