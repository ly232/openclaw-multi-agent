"""DuckDB schema and query builder for the observability dashboard.

Concurrency model: each HTTP handler opens its own DuckDB connection for
the duration of a single request.  This avoids TOCTOU races on shared
connection state (cursor description, etc.) when multiple threads call
.execute() simultaneously.

The collector thread uses a separate long-lived connection obtained via
get_db() — it never contends with short-lived HTTP connections because
DuckDB supports multiple write-mode connections from the same process.
"""

import json
import time
import threading
import duckdb

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id VARCHAR PRIMARY KEY,
    timestamp TIMESTAMP,
    channel VARCHAR,
    account_id VARCHAR,
    session_id VARCHAR,
    user_message TEXT,
    assistant_response TEXT,
    root_agent VARCHAR,
    agents_involved JSON,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    status VARCHAR DEFAULT 'ok',
    trace_file VARCHAR,
    trace_offset BIGINT
);

CREATE TABLE IF NOT EXISTS trace_events (
    id BIGINT PRIMARY KEY,
    interaction_id VARCHAR REFERENCES interactions(interaction_id),
    seq INTEGER,
    ts BIGINT,
    agent VARCHAR,
    event_type VARCHAR,
    detail JSON
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id VARCHAR PRIMARY KEY,
    interaction_id VARCHAR REFERENCES interactions(interaction_id),
    evaluator_model VARCHAR,
    prompt_version VARCHAR,
    correctness INTEGER,
    relevance INTEGER,
    completeness INTEGER,
    clarity INTEGER,
    overall FLOAT,
    timestamp TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_account ON interactions(account_id);
CREATE INDEX IF NOT EXISTS idx_interactions_agent ON interactions(root_agent);
CREATE INDEX IF NOT EXISTS idx_trace_events_interaction ON trace_events(interaction_id);
"""

SUMMARY_7D = """SELECT COUNT(*) AS interactions,
    COALESCE(SUM(total_tokens), 0) AS total_tokens,
    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
    COALESCE(AVG(latency_ms) FILTER (WHERE latency_ms > 0), 0)::BIGINT AS avg_latency_ms,
    COALESCE(SUM(total_tokens) * 0.00000014 + SUM(output_tokens) * 0.00000028, 0) AS est_cost_usd,
    COUNT(*) FILTER (WHERE status != 'ok') AS failures,
    COALESCE(100.0 * COUNT(*) FILTER (WHERE agents_involved IS NOT NULL
        AND json_array_length(agents_involved) > 1) / NULLIF(COUNT(*), 0), 0) AS multi_agent_pct
FROM interactions WHERE timestamp >= now() - INTERVAL '7 days'"""

TOP_ACCOUNTS = """SELECT account_id, COUNT(*) AS messages,
    SUM(total_tokens) AS tokens,
    SUM(total_tokens) * 0.00000014 + SUM(output_tokens) * 0.00000028 AS cost
FROM interactions WHERE timestamp >= now() - INTERVAL '7 days'
GROUP BY account_id ORDER BY tokens DESC LIMIT ?"""

TOP_AGENTS = """SELECT root_agent AS agent, COUNT(*) AS requests,
    SUM(total_tokens) AS tokens, AVG(latency_ms)::BIGINT AS avg_latency_ms
FROM interactions WHERE timestamp >= now() - INTERVAL '7 days'
GROUP BY root_agent ORDER BY requests DESC LIMIT ?"""

ACCOUNT_MESSAGES = """SELECT timestamp, user_message, root_agent AS agent, total_tokens AS tokens
FROM interactions WHERE account_id = ? AND timestamp >= now() - INTERVAL '7 days'
ORDER BY timestamp DESC LIMIT ? OFFSET ?"""

AGENT_INTERACTIONS = """SELECT timestamp, account_id,
    substring(user_message, 1, 100) AS task, total_tokens AS tokens
FROM interactions WHERE root_agent = ? AND timestamp >= now() - INTERVAL '7 days'
ORDER BY timestamp DESC LIMIT ? OFFSET ?"""

AGENT_METRICS = """SELECT root_agent AS agent, COUNT(*) AS requests,
    AVG(total_tokens)::BIGINT AS avg_tokens, AVG(latency_ms)::BIGINT AS avg_latency_ms
FROM interactions WHERE timestamp >= now() - INTERVAL '7 days'
GROUP BY root_agent ORDER BY requests DESC"""

MESSAGE_BY_ID = "SELECT * FROM interactions WHERE interaction_id = ?"
TRACE_EVENTS = "SELECT * FROM trace_events WHERE interaction_id = ? ORDER BY seq"


class Database:
    def __init__(self, path: str = "~/.openclaw/observability.duckdb", read_only: bool | None = None):
        self._path = path
        self._lock = threading.Lock()
        self._conn: duckdb.DuckDBPyConnection | None = None

    def open(self, retries: int = 3, base_delay: float = 0.1) -> None:
        """Open connection. Retries on lock conflict."""
        if self._conn is not None:
            return
        with self._lock:
            if self._conn is not None:
                return
            last_exc = None
            for attempt in range(retries):
                try:
                    self._conn = duckdb.connect(str(self._path), read_only=False)
                    for stmt in SCHEMA_SQL.split(";"):
                        s = stmt.strip()
                        if s:
                            self._conn.execute(s)
                    return
                except duckdb.IOException as e:
                    last_exc = e
                    if attempt < retries - 1:
                        time.sleep(base_delay * (attempt + 1))
            raise last_exc  # type: ignore

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self.open()
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def execute_dicts(self, sql: str, *params) -> list[dict]:
        """Execute a query and return results as a list of dicts.

        Materializes column names and rows into Python objects before
        returning, so the connection can be safely reused or closed.
        """
        cur = self.conn.execute(sql, params)
        # Materialize description into a Python list immediately.
        # DuckDB's result.description reads lazily from C cursor state
        # and can be overwritten by concurrent execute() on the same conn.
        cols = [cur.description[i][0] for i in range(len(cur.description))]
        rows = cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def insert_interaction(self, row: dict) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO interactions
               (interaction_id, timestamp, channel, account_id, session_id,
                user_message, assistant_response, root_agent, agents_involved,
                input_tokens, output_tokens, total_tokens, reasoning_tokens,
                latency_ms, status, trace_file, trace_offset)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["interaction_id"], row.get("timestamp"), row.get("channel"),
             row.get("account_id"), row.get("session_id"),
             row.get("user_message"), row.get("assistant_response"),
             row.get("root_agent"), json.dumps(row.get("agents_involved", [])),
             row.get("input_tokens", 0), row.get("output_tokens", 0),
             row.get("total_tokens", 0), row.get("reasoning_tokens", 0),
             row.get("latency_ms", 0), row.get("status", "ok"),
             row.get("trace_file"), row.get("trace_offset", 0)),
        )

    def insert_trace_event(self, row: dict) -> None:
        self.conn.execute(
            """INSERT INTO trace_events
               (id, interaction_id, seq, ts, agent, event_type, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], row["interaction_id"], row["seq"], row["ts"],
             row["agent"], row["event_type"], json.dumps(row.get("detail", {}))),
        )

    def insert_evaluation(self, row: dict) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO evaluations
               (evaluation_id, interaction_id, evaluator_model, prompt_version,
                correctness, relevance, completeness, clarity, overall)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["evaluation_id"], row["interaction_id"],
             row.get("evaluator_model", "deepseek/deepseek-v4-flash"),
             row.get("prompt_version", "v1"),
             row.get("correctness"), row.get("relevance"),
             row.get("completeness"), row.get("clarity"), row.get("overall")),
        )

    def prune_old_data(self, retention_days: int = 7) -> int:
        result = self.conn.execute(
            f"DELETE FROM interactions WHERE timestamp < now() - INTERVAL '{retention_days} days'"
        )
        return result.rowcount


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    """Return the shared collector connection (long-lived, read-write)."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
                _db.open(retries=1)  # crash fast on failure
    return _db


def get_request_db() -> Database:
    """Return a fresh connection for a single HTTP request.

    Each call opens a new connection, so concurrent requests don't
    share cursor state.  The caller MUST close() after use.
    """
    db = Database()
    db.open()
    return db


def close_db() -> None:
    global _db
    if _db is not None:
        _db.close()
        _db = None
