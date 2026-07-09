# TOOLS.md — Orchestrator Notes

## Session Tools

These are your primary tools for routing. Use them deliberately.

- `sessions_list` — check available specialist sessions
- `sessions_history` — read past specialist interactions (debugging only)
- `sessions_send` — forward a request to a specialist and wait for reply
- `sessions_spawn` — create a focused sub-agent for multi-step workflows
- `session_status` — check agent health

## Session Keys (for sessions_send)

| Specialist | Session Key |
|------------|-------------|
| Coding     | `agent:coding:main` |
| Research   | `agent:research:main` |
| General    | `agent:general:main` |

## Important

- The specialist agents need to exist in `agents.list` in the config for these session keys to work.
- Agent-to-agent messaging must be enabled in config (`tools.agentToAgent.enabled: true`).
- `sessions_send` with a timeout waits for the response — use this for synchronous routing.
