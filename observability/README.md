# OpenClaw Observability Dashboard

A standalone web application for operational visibility into your OpenClaw multi-agent system.

## Architecture

```text
OpenClaw Runtime  →  Log Collector  →  DuckDB  →  FastAPI  →  React Dashboard
```

The **Log Collector** reads `*.trajectory.jsonl` files from your OpenClaw session store, parses them into structured interaction records, and inserts them into DuckDB. The **FastAPI** server serves a JSON API that the **React** frontend consumes.

## Quick Start

### 1. Install dependencies

```bash
cd observability/backend
uv sync
```

### 2. Run the collector (one-shot)

```bash
uv run python collector.py --once
```

### 3. Start the web server

```bash
uv run python server.py
# → http://127.0.0.1:8080
```

### 4. Start the frontend (separate terminal)

```bash
cd observability/frontend
npm install
npm run dev
# → http://127.0.0.1:5173
```

Open http://127.0.0.1:5173 in your browser.

## Running the Collector as a Daemon

### Option A: Background process (simple)

```bash
cd observability/backend
nohup uv run python collector.py > ~/.openclaw/observability/collector.log 2>&1 &
echo $! > ~/.openclaw/observability/collector.pid
```

Stop with:

```bash
kill $(cat ~/.openclaw/observability/collector.pid)
```

### Option B: macOS LaunchAgent

Create `~/Library/LaunchAgents/com.openclaw.observability-collector.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.observability-collector</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uv</string>
        <string>run</string>
        <string>--directory</string>
        <string>/Users/YOU/github/openclaw-multi-agent/observability/backend</string>
        <string>python</string>
        <string>collector.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOU/.openclaw/observability/collector.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOU/.openclaw/observability/collector.log</string>
</dict>
</plist>
```

Then:

```bash
launchctl load ~/Library/LaunchAgents/com.openclaw.observability-collector.plist
launchctl start com.openclaw.observability-collector
```

### Option C: systemd (Linux)

```ini
[Unit]
Description=OpenClaw Observability Collector

[Service]
Type=simple
ExecStart=/usr/local/bin/uv run --directory /home/YOU/github/openclaw-multi-agent/observability/backend python collector.py
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
```

### Option D: Cron (simplest)

```bash
crontab -e
# Add:
*/5 * * * * cd /Users/YOU/github/openclaw-multi-agent/observability/backend && uv run python collector.py --once
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

Lists WeChat accounts ranked by token usage. Click any account to see their recent messages.

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

## Database

The collector stores ingested data in a **DuckDB** file:



### Schema

Three tables:

- **interactions** — one row per user-assistant exchange (timestamp, channel, account, message text, agent, token usage, latency, status)
- **trace_events** — execution trace events for each interaction (agent, event type, timestamp, detail)
- **evaluations** — quality evaluation scores (correctness, relevance, completeness, clarity, overall)

### Query Directly with DuckDB CLI



### Example Queries



### State File

The collector tracks which trajectory lines it has already read in:



Delete this file to force a full re-ingestion.

---

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

---

### Data Retention

The collector automatically prunes interactions older than **7 days** on every ingest run
(`--once` and daemon mode). This keeps the DuckDB file from growing unboundedly.

To change the retention period, edit the `retention_days` argument in
`collector.prune_old_data()`. To keep data forever, set `retention_days=0`
(which disables pruning).
