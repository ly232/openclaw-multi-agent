const API = "/api"
const FETCH_TIMEOUT = 5_000

async function fetchWithTimeout(url: string, options?: RequestInit): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

async function get<T>(path: string, retries = 3): Promise<T | null> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const res = await fetchWithTimeout(`${API}${path}`)
      if (!res.ok) {
        console.warn(`GET ${path}: ${res.status} (attempt ${attempt + 1}/${retries})`)
        if (attempt === retries - 1) return null
        await new Promise(r => setTimeout(r, 300 * (attempt + 1)))
        continue
      }
      return res.json()
    } catch (err) {
      console.warn(`GET ${path} error:`, err, `(attempt ${attempt + 1}/${retries})`)
      if (attempt === retries - 1) return null
      await new Promise(r => setTimeout(r, 300 * (attempt + 1)))
    }
  }
  return null
}

async function post<T>(path: string, body: unknown): Promise<T | null> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetchWithTimeout(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        console.warn(`POST ${path}: ${res.status} (attempt ${attempt + 1}/3)`)
        if (attempt === 2) return null
        await new Promise(r => setTimeout(r, 300 * (attempt + 1)))
        continue
      }
      return res.json()
    } catch (err) {
      console.warn(`POST ${path} error:`, err, `(attempt ${attempt + 1}/3)`)
      if (attempt === 2) return null
      await new Promise(r => setTimeout(r, 300 * (attempt + 1)))
    }
  }
  return null
}

export interface Summary {
  interactions: number; total_tokens: number; reasoning_tokens: number;
  avg_latency_ms: number; est_cost_usd: number; failures: number; multi_agent_pct: number;
}
export function getSummary() { return get<Summary>("/dashboard/summary") }

export interface AccountRow { account_id: string; messages: number; tokens: number; cost: number }
export function getAccounts(limit = 10) { return get<AccountRow[]>(`/accounts?limit=${limit}`) }

export interface MsgRow { timestamp: string; user_message: string; agent: string; tokens: number; account_id?: string }
export function getAccountMessages(id: string, limit = 10, offset = 0) {
  return get<MsgRow[]>(`/accounts/${id}/messages?limit=${limit}&offset=${offset}`)
}

export interface AgentRow { agent: string; requests: number; tokens: number; avg_latency_ms: number }
export interface AgentMetrics { agent: string; requests: number; avg_tokens: number; avg_latency_ms: number }
export interface AgentsResponse { agents: AgentRow[]; metrics: AgentMetrics[] }
export function getAgents(limit = 10) { return get<AgentsResponse>(`/agents?limit=${limit}`) }

export function getAgentInteractions(id: string, limit = 10, offset = 0) {
  return get<MsgRow[]>(`/agents/${id}/interactions?limit=${limit}&offset=${offset}`)
}

export interface Interaction {
  interaction_id: string; timestamp: string; account_id: string;
  user_message: string; assistant_response: string; root_agent: string;
  total_tokens: number; input_tokens: number; output_tokens: number;
  reasoning_tokens: number; latency_ms: number; status: string;
}
export function getMessage(id: string) { return get<Interaction | null>(`/messages/${id}`) }

export interface TraceEvent { id: number; seq: number; ts: number; agent: string; event_type: string; detail: string }
export function getTrace(id: string) { return get<TraceEvent[]>(`/messages/${id}/trace`) }

export function postEvaluation(id: string, scores: { correctness: number; relevance: number; completeness: number; clarity: number; overall: number }) {
  return post<{ ok: boolean }>(`/messages/${id}/evaluate`, scores)
}
