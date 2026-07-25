import { useEffect, useRef, useState } from "react"
import {
  getAccounts, getAgents, getSummary,
  Summary, AccountRow, AgentsResponse,
} from "../api/client"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import { Activity, DollarSign, AlertTriangle, Zap, Users, Bot, RefreshCw, Wifi, WifiOff } from "lucide-react"

const POLL_MS = 15_000

const DAY_OPTIONS = [
  { label: "7 days", value: 7 },
  { label: "14 days", value: 14 },
  { label: "21 days", value: 21 },
  { label: "1 month", value: 30 },
]

export default function Dashboard() {
  const [s, setS] = useState<Summary | null>(null)
  const [accts, setAccts] = useState<AccountRow[]>([])
  const [ag, setAg] = useState<AgentsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [connected, setConnected] = useState(true)
  const [acctDays, setAcctDays] = useState(7)
  const [agentDays, setAgentDays] = useState(7)
  const mounted = useRef(true)

  // Individual fetch helpers for dropdown-driven re-fetches
  const fetchAccounts = (days: number) => {
    getAccounts(5, days).then(accounts => {
      if (mounted.current) {
        setAccts(accounts ?? [])
      }
    })
  }

  const fetchAgents = (days: number) => {
    getAgents(5, days).then(agents => {
      if (mounted.current) {
        setAg(agents ?? { agents: [], metrics: [] })
      }
    })
  }

  useEffect(() => {
    // Reset mounted flag — in Strict Mode the ref persists across mounts.
    mounted.current = true

    const fetch = () => {
      setLoading(true)
      console.log('[dashboard] fetch cycle starting')
      const start = Date.now()
      Promise.all([
        getSummary(),
        getAccounts(5, acctDays),
        getAgents(5, agentDays),
      ]).then(([summary, accounts, agents]) => {
        const elapsed = Date.now() - start
        if (!mounted.current) { console.log('[dashboard] unmounted, discarding'); return }
        console.log(`[dashboard] data received in ${elapsed}ms:`, {
          summary: summary ? `${summary.interactions} interactions` : null,
          accounts: accounts ? `${accounts.length} accounts` : null,
          agents: agents ? `${agents.agents?.length || 0} agents` : null,
        })
        if (summary && typeof summary.interactions === 'number') {
          setS(summary)
          setConnected(true)
        } else {
          console.warn('[dashboard] summary missing interactions key:', summary)
          setConnected(false)
        }
        setAccts(accounts ?? [])
        setAg(agents ?? { agents: [], metrics: [] })
        setLoading(false)
      })
    }
    fetch()
    const interval = setInterval(fetch, POLL_MS)
    return () => {
      mounted.current = false
      clearInterval(interval)
    }
  }, [acctDays, agentDays])

  const cards = [
    { title: "Interactions", value: s?.interactions ?? "-", icon: Activity },
    { title: "Tokens", value: (s?.total_tokens ?? 0).toLocaleString(), icon: Zap },
    { title: "Est. Cost", value: "$" + (s?.est_cost_usd ?? 0).toFixed(2), icon: DollarSign },
    { title: "Avg Latency", value: (s?.avg_latency_ms ?? 0) + "ms", icon: Activity },
    { title: "Failures", value: (s?.failures ?? 0) + " (" + (s?.multi_agent_pct ?? 0).toFixed(1) + "%)", icon: AlertTriangle },
    { title: "Multi-Agent", value: (s?.multi_agent_pct ?? 0).toFixed(1) + "%", icon: Users },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        {loading && <RefreshCw size={16} className="animate-spin text-gray-400" />}
        {!loading && (connected
          ? <Wifi size={14} className="text-green-500" />
          : <WifiOff size={14} className="text-red-500" />
        )}
      </div>
      <div className="grid grid-cols-3 gap-4">
        {cards.map(c => (
          <Card key={c.title}>
            <CardHeader className="flex flex-row items-center gap-2 pb-2">
              <c.icon size={18} className="text-gray-500" />
              <CardTitle className="text-sm font-medium">{c.title}</CardTitle>
            </CardHeader>
            <CardContent><p className="text-2xl font-bold">{c.value}</p></CardContent>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Top Accounts (tokens)</CardTitle>
            <select
              className="border rounded px-2 py-1 text-sm bg-white"
              value={acctDays}
              onChange={e => {
                const days = Number(e.target.value)
                setAcctDays(days)
                fetchAccounts(days)
              }}
            >
              {DAY_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={accts}>
                <XAxis dataKey="account_id" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={v => v >= 1_000_000 ? (v / 1_000_000).toFixed(1) + 'M' : v >= 1_000 ? (v / 1_000).toFixed(0) + 'K' : v} /><Tooltip />
                <Bar dataKey="tokens" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Agent Usage</CardTitle>
            <select
              className="border rounded px-2 py-1 text-sm bg-white"
              value={agentDays}
              onChange={e => {
                const days = Number(e.target.value)
                setAgentDays(days)
                fetchAgents(days)
              }}
            >
              {DAY_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={ag?.agents ?? []}>
                <XAxis dataKey="agent" tick={{ fontSize: 11 }} />
                <YAxis /><Tooltip />
                <Bar dataKey="requests" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
