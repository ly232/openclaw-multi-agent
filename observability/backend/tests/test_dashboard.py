"""Unit tests for the observability dashboard backend.

Tests cover:
- DuckDB SQL compilation for all query functions
- API endpoint responses via FastAPI TestClient
- Regression: no `?` placeholder inside INTERVAL expressions
"""

import re
import pytest
import duckdb
from fastapi.testclient import TestClient
from server import app

# ── helpers ──────────────────────────────────────────────────────────────────

# Schema matching the real `interactions` table (minimum columns needed by SQL).
_INTERACTIONS_SCHEMA = """
    CREATE TEMP TABLE interactions (
        interaction_id VARCHAR,
        timestamp TIMESTAMP,
        account_id VARCHAR,
        root_agent VARCHAR,
        agents_involved JSON,
        input_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        reasoning_tokens INTEGER,
        latency_ms INTEGER,
        status VARCHAR
    )
"""

# All SQL-producing functions in database.py that accept `days`.
_SQL_FUNCS = ["summary", "top_accounts", "top_agents", "agent_metrics"]

_DAYS_VALUES = [1, 7, 14, 21, 30]


def _sql_has_bad_interval_placeholder(sql: str) -> bool:
    """Return True if SQL contains the old bug pattern ``INTERVAL ? DAY``."""
    return bool(re.search(r"INTERVAL\s+\?\s+DAY", sql, re.IGNORECASE))


def _sql_has_valid_interval(sql: str) -> bool:
    """Return True if SQL contains ``INTERVAL '<number>' DAY`` (DuckDB syntax)."""
    # DuckDB supports both INTERVAL '7' DAY and INTERVAL 7 DAY
    return bool(re.search(r"INTERVAL\s+'?\d+'?\s+DAY", sql, re.IGNORECASE))


def _sql_has_placeholder(sql: str) -> bool:
    """Return True if the SQL still contains any `?` placeholders."""
    return "?" in sql


# ── SQL compilation tests ────────────────────────────────────────────────────


class TestSqlCompilation:
    """Verify every query function produces valid DuckDB SQL."""

    @pytest.fixture(autouse=True)
    def _in_memory_db(self):
        """Create a DuckDB in-memory connection with the interactions table."""
        conn = duckdb.connect(":memory:")
        conn.execute(_INTERACTIONS_SCHEMA)
        self.conn = conn
        yield
        conn.close()

    def check_sql_compiles(self, sql: str, params: tuple = None):
        """Assert that DuckDB can EXPLAIN the given SQL without raising.

        Args:
            sql: The SQL string (may contain ``?`` placeholders).
            params: Optional tuple of parameter values for ``?`` placeholders.
        """
        if _sql_has_placeholder(sql):
            # SQL has prepared-statement placeholders – provide dummy values
            self.conn.execute(f"EXPLAIN {sql}", params or (1,))
        else:
            self.conn.execute(f"EXPLAIN {sql}")

    # ── parametrized: all SQL functions × all days values ─────────────────

    @pytest.mark.parametrize("func_name", _SQL_FUNCS)
    @pytest.mark.parametrize("days", _DAYS_VALUES)
    def test_query_compiles(self, func_name: str, days: int):
        """Every query function produces compilable SQL for every days value."""
        import database as db
        fn = getattr(db, func_name)
        sql = fn(days=days)
        # top_accounts and top_agents have LIMIT ? – provide a dummy value
        if func_name in ("top_accounts", "top_agents"):
            self.check_sql_compiles(sql, params=(10,))
        else:
            self.check_sql_compiles(sql)

    # ── regression: no '?' inside INTERVAL ─────────────────────────────────

    @pytest.mark.parametrize("func_name", _SQL_FUNCS)
    @pytest.mark.parametrize("days", _DAYS_VALUES)
    def test_no_placeholder_inside_interval(self, func_name: str, days: int):
        """INTERVAL uses a literal number, not a '?' placeholder."""
        import database as db
        fn = getattr(db, func_name)
        sql = fn(days=days)
        assert not _sql_has_bad_interval_placeholder(sql), (
            f"{func_name}({days}) returned SQL with 'INTERVAL ? DAY': {sql}"
        )
        assert _sql_has_valid_interval(sql), (
            f"{func_name}({days}) returned SQL without a valid INTERVAL: {sql}"
        )

    # ── SQL parameter safety: '?' still works for LIMIT ────────────────────

    def test_top_accounts_has_limit_placeholder(self):
        """top_accounts should still use '?' for LIMIT (outside INTERVAL)."""
        import database as db
        sql = db.top_accounts(days=14)
        assert "LIMIT ?" in sql, f"top_accounts SQL missing LIMIT ?: {sql}"
        assert _sql_has_valid_interval(sql)

    def test_top_agents_has_limit_placeholder(self):
        """top_agents should still use '?' for LIMIT (outside INTERVAL)."""
        import database as db
        sql = db.top_agents(days=30)
        assert "LIMIT ?" in sql, f"top_agents SQL missing LIMIT ?: {sql}"
        assert _sql_has_valid_interval(sql)

    # ── edge cases ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize("func_name", _SQL_FUNCS)
    def test_default_days(self, func_name: str):
        """Default days=7 should still produce valid SQL."""
        import database as db
        fn = getattr(db, func_name)
        sql = fn()  # no explicit days
        if func_name in ("top_accounts", "top_agents"):
            self.check_sql_compiles(sql, params=(10,))
        else:
            self.check_sql_compiles(sql)
        assert not _sql_has_bad_interval_placeholder(sql)
        assert _sql_has_valid_interval(sql)


# ── API endpoint tests ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Start FastAPI with a temporary database file.

    Patches Database to use a tmp_path file so tests never write to the
    real observability DB.  Seeds one row via /api/seed for query tests.
    """
    db_path = tmp_path_factory.mktemp("obs_tests") / "test.duckdb"

    # --- patch Database.__init__ to use our temp path ---
    import database
    original_init = database.Database.__init__
    def _patched_init(self, path=None, read_only=None):
        original_init(self, path=str(db_path), read_only=read_only)
    database.Database.__init__ = _patched_init
    database._db = None  # reset singleton so get_db() reopens fresh

    with TestClient(app) as c:
        yield c


class TestServerEndpoints:
    """Verify HTTP endpoints return 200 and correct response shapes."""

    def _seed(self, client):
        """Ensure at least one row exists; idempotent (calls /api/seed)."""
        resp = client.post("/api/seed")
        return resp.json()

    # ── health / basic structure ───────────────────────────────────────────

    @pytest.mark.parametrize("days", _DAYS_VALUES)
    def test_summary_returns_json(self, client, days: int):
        """GET /api/dashboard/summary returns 200 for valid days."""
        self._seed(client)
        resp = client.get(f"/api/dashboard/summary?days={days}")
        assert resp.status_code == 200, f"summary days={days}: {resp.text}"
        body = resp.json()
        assert isinstance(body, dict), f"expected dict, got {type(body)}"

    @pytest.mark.parametrize("days", _DAYS_VALUES)
    @pytest.mark.parametrize("limit", [1, 5, 10])
    def test_accounts_returns_ok(self, client, days: int, limit: int):
        """GET /api/accounts returns 200 for valid days+limit."""
        self._seed(client)
        resp = client.get(f"/api/accounts?days={days}&limit={limit}")
        assert resp.status_code == 200, f"accounts days={days} limit={limit}: {resp.text}"

    @pytest.mark.parametrize("days", _DAYS_VALUES)
    @pytest.mark.parametrize("limit", [1, 5, 10])
    def test_agents_returns_ok(self, client, days: int, limit: int):
        """GET /api/agents returns 200 for valid days+limit."""
        self._seed(client)
        resp = client.get(f"/api/agents?days={days}&limit={limit}")
        assert resp.status_code == 200, f"agents days={days} limit={limit}: {resp.text}"
        body = resp.json()
        # Response shape: {"agents": [...], "metrics": [...]}
        assert "agents" in body
        assert "metrics" in body

    # ── detailed endpoints ─────────────────────────────────────────────────

    def test_account_messages(self, client):
        """GET /api/accounts/{id}/messages returns 200."""
        seed = self._seed(client)
        aid = seed.get("interaction_id", "smoke-test-user")
        resp = client.get(f"/api/accounts/{aid}/messages?limit=5")
        assert resp.status_code == 200

    def test_agent_interactions(self, client):
        """GET /api/agents/{id}/interactions returns 200."""
        self._seed(client)
        resp = client.get("/api/agents/smoke-test-agent/interactions?limit=5")
        assert resp.status_code == 200

    def test_get_message(self, client):
        """GET /api/messages/{id} returns 200."""
        seed = self._seed(client)
        mid = seed.get("interaction_id", "nonexistent")
        resp = client.get(f"/api/messages/{mid}")
        # 200 even if not found (returns None → JSON null → 200)
        assert resp.status_code == 200

    def test_get_trace(self, client):
        """GET /api/messages/{id}/trace returns 200."""
        seed = self._seed(client)
        mid = seed.get("interaction_id", "nonexistent")
        resp = client.get(f"/api/messages/{mid}/trace")
        assert resp.status_code == 200

    # ── edge: missing params use defaults ──────────────────────────────────

    def test_summary_no_days(self, client):
        """Default days=7 is used when query param omitted."""
        self._seed(client)
        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200

    def test_accounts_no_params(self, client):
        """Default days=7 and limit=10 used when params omitted."""
        self._seed(client)
        resp = client.get("/api/accounts")
        assert resp.status_code == 200

    def test_agents_no_params(self, client):
        """Default days=7 and limit=10 used when params omitted."""
        self._seed(client)
        resp = client.get("/api/agents")
        assert resp.status_code == 200

    # ── edge: boundary days values ─────────────────────────────────────────

    def test_summary_days_1(self, client):
        """Minimum days=1 should work."""
        self._seed(client)
        resp = client.get("/api/dashboard/summary?days=1")
        assert resp.status_code == 200

    def test_summary_days_31(self, client):
        """Maximum days=31 should work (FastAPI validation le=31)."""
        self._seed(client)
        resp = client.get("/api/dashboard/summary?days=31")
        assert resp.status_code == 200

    # ── validation rejection ───────────────────────────────────────────────

    def test_summary_days_0_rejected(self, client):
        """days=0 violates ge=1 → 422."""
        resp = client.get("/api/dashboard/summary?days=0")
        assert resp.status_code == 422

    def test_summary_days_32_rejected(self, client):
        """days=32 violates le=31 → 422."""
        resp = client.get("/api/dashboard/summary?days=32")
        assert resp.status_code == 422

    def test_accounts_negative_limit_rejected(self, client):
        """Negative limit violates ge=1 → 422."""
        resp = client.get("/api/accounts?limit=-1")
        assert resp.status_code == 422

    def test_agents_large_limit_rejected(self, client):
        """Limit > 100 violates le=100 → 422."""
        resp = client.get("/api/agents?limit=200")
        assert resp.status_code == 422
