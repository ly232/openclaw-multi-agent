# OpenClaw Observability Dashboard

A standalone web application for operational visibility into your OpenClaw multi-agent system.

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│                 Server Process                        │
│                                                       │
│  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │   FastAPI Handlers   │  │  Collector Thread    │  │
│  │   (thread pool)      │  │  (daemon, polls      │  │
│  │                      │  │   every 30s)         │  │
│  └─────────┬────────────┘  └──────────┬───────────┘  │
│            │                          │              │
│            └──────────┬───────────────┘              │
│                       ▼                              │
│        ┌─────────────────────────────┐               │
│        │  Single DuckDB Connection  │               │
│        │  (read-write, shared)      │               │
│        └─────────────────────────────┘               │
└─────────────────────────────────────────────────────┘
                           │
                           ▼
              DuckDB file (~/.openclaw/observability.duckdb)
```

The **Collector** runs as a daemon thread **inside** the FastAPI server process. Both share a single read-write DuckDB connection. This avoids cross-process file lock contention, which DuckDB's native format does not support (only one writer process allowed). DuckDB handles concurrent reads and writes on the same connection within a single process via MVCC.

The Collector reads `*.trajectory.jsonl` files from `~/.openclaw/agents/*/sessions/`, parses them into structured interaction records, and inserts them into DuckDB. The FastAPI server serves a JSON API that the React frontend consumes.

## Quick Start

### 1. Install dependencies

```bash
cd observability/backend
uv sync
cd ../frontend
npm install
```

### 2. Start everything

```bash
# Terminal 1: backend (includes collector thread)
cd observability/backend
uv run python server.py
# → http://127.0.0.1:8080

# Terminal 2: frontend
cd observability/frontend
npm run dev
# → http://127.0.0.1:5173
```

Open http://127.0.0.1:5173 in your browser.

### Run a one-shot collection (without starting the server)

```bash
cd observability/backend
uv run python -c "from collector import collect_once; collect_once()"
```

### Run smoke tests

```bash
cd observability/backend
source .venv/bin/activate
python ../smoke_test.py
```

## User Guide

### Dashboard

The homepage shows system-level summary cards for the last 7 days:

- **Interactions** — total user-LLM exchanges
- **Tokens** — total tokens consumed
- **Est. Cost** — estimated API cost (based on model pricing)
- **Avg Latency** — average response time
- **Failures** — count and percentage of failed interactions
- **Multi-Agent %** — percentage of interactions that involved more than one agent

Below the cards are bar charts for top accounts (by token usage) and top agents (by request count).

### Accounts

Lists accounts ranked by token usage. Click any account to see their recent messages.

### Agents

Shows per-agent performance metrics (requests, avg tokens, avg latency). Click any agent to see its recent interactions.

### Messages

View a single interaction's full detail: user message, assistant response, token usage, latency, and the execution trace timeline.

The **Quick Evaluation** panel lets you score the interaction on correctness, relevance, completeness, and clarity (1-5). Scores are stored in DuckDB for later aggregation.

### Execution Trace

Each message has a timeline showing the execution path: orchestrator decision → agent invocations → tool calls → model responses → final reply.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/dashboard/summary | 7-day system summary |
| GET | /api/accounts | Top accounts |
| GET | /api/accounts/{id}/messages | Account messages |
| GET | /api/agents | Top agents + metrics |
| GET | /api/agents/{id}/interactions | Agent interactions |
| GET | /api/messages/{id} | Message detail |
| GET | /api/messages/{id}/trace | Execution trace events |
| POST | /api/messages/{id}/evaluate | Save evaluation scores |
| POST | /api/seed | Insert test data (smoke tests) |

## Database

The collector stores ingested data in a **DuckDB** file at:

```
~/.openclaw/observability.duckdb
```

### Schema

Three tables:

- **interactions** — one row per user-assistant exchange (timestamp, channel, account, message text, agent, token usage, latency, status)
- **trace_events** — execution trace events for each interaction (agent, event type, timestamp, detail)
- **evaluations** — quality evaluation scores (correctness, relevance, completeness, clarity, overall)

### Query Directly with DuckDB CLI

```bash
# Start the server first so the collector syncs the latest trajectory data
duckdb -readonly ~/.openclaw/observability.duckdb
```

> **Important:** Always start `server.py` first before querying with the CLI.
> The collector runs as a thread inside the server process — it polls
> trajectory files every 30 seconds and ingests new interactions into DuckDB.
> Without the server running, you're querying stale data.
>
> Always use the `-readonly` flag when connecting while the server is running.
> The server holds a write lock on the database, and the CLI defaults to write
> mode which will fail with a lock conflict.

### Example Queries

```sql
-- Last 10 interactions
SELECT timestamp, account_id, root_agent, total_tokens
FROM interactions
ORDER BY timestamp DESC
LIMIT 10;

-- Token usage by agent
SELECT root_agent,
       COUNT(*) AS requests,
       SUM(total_tokens) AS tokens
FROM interactions
GROUP BY root_agent
ORDER BY tokens DESC;

-- Recent evaluations
SELECT i.interaction_id,
       e.correctness,
       e.relevance,
       e.overall
FROM interactions i
JOIN evaluations e ON i.interaction_id = e.interaction_id
ORDER BY e.timestamp DESC
LIMIT 10;
```

### State File

The collector tracks which trajectory lines it has already read in:

```
~/.openclaw/observability/collector_state.json
```

Delete this file to force a full re-ingestion.

## Data Source

The collector reads from `~/.openclaw/agents/*/sessions/*.trajectory.jsonl`. It tracks its position per file via `~/.openclaw/observability/collector_state.json` so repeated runs only ingest new data.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Database | DuckDB (embedded, file-based) |
| Backend | Python + FastAPI + Uvicorn |
| Frontend | React + TypeScript + Vite |
| Charts | Recharts |
| Tables | TanStack Table |
| Styling | Tailwind CSS |

## Data Retention

The collector automatically prunes interactions older than **7 days** on every ingest cycle. To change the retention period, edit the `retention_days` keyword in `database.py`'s `prune_old_data()` method. To keep data forever, pass `retention_days=0` (disables pruning).

## Troubleshooting

### "Could not set lock on file"

You (or another process) opened the DuckDB file without the `-readonly` flag.
The server holds a write lock — use `duckdb -readonly ...` for ad-hoc queries.

### Backend won't start

Check `http://127.0.0.1:8080` — if another process is using the port, kill it:

```bash
lsof -ti :8080 | xargs kill
```

### All metrics show zero

Check the server logs for errors:

```bash
tail -f /tmp/observability-server.log
```

Common causes: no trajectory files exist yet, or the collector thread is still in its first 30-second poll cycle.
