"""FastAPI server for the observability dashboard."""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import get_db, SUMMARY_7D, TOP_ACCOUNTS, TOP_AGENTS, \
    ACCOUNT_MESSAGES, AGENT_INTERACTIONS, AGENT_METRICS, MESSAGE_BY_ID, TRACE_EVENTS

app = FastAPI(title="OpenClaw Observability")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def dicts(sql: str, *params):
    db = get_db()
    rows = db.conn.execute(sql, params).fetchall()
    cols = [d[0] for d in db.conn.description]
    return [dict(zip(cols, r)) for r in rows]


@app.get("/api/dashboard/summary")
def dashboard_summary():
    rows = dicts(SUMMARY_7D)
    return rows[0] if rows else {}


@app.get("/api/accounts")
def list_accounts(limit: int = Query(10, ge=1, le=100)):
    return dicts(TOP_ACCOUNTS, limit)


@app.get("/api/accounts/{account_id}/messages")
def account_messages(account_id: str, limit: int = Query(10, ge=1, le=100), offset: int = 0):
    return dicts(ACCOUNT_MESSAGES, account_id, limit, offset)


@app.get("/api/agents")
def list_agents(limit: int = Query(10, ge=1, le=100)):
    return {"agents": dicts(TOP_AGENTS, limit), "metrics": dicts(AGENT_METRICS)}


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


class EvalRequest(BaseModel):
    correctness: int
    relevance: int
    completeness: int
    clarity: int
    overall: float = 0.0
    evaluator_model: str = "deepseek/deepseek-v4-flash"


@app.post("/api/messages/{message_id}/evaluate")
def evaluate_message(message_id: str, req: EvalRequest):
    from database import get_db
    import uuid
    db = get_db()
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


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
