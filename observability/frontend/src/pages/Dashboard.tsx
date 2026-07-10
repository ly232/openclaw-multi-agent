import { useEffect, useRef, useState } from "react"
import {
  getAccounts, getAgents, getSummary,
  Summary, AccountRow, AgentsResponse,
} from "../api/client"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import { Activity, DollarSign, AlertTriangle, Zap, Users, Bot, RefreshCw } from "lucide-react"

const POLL_MS = 15_000

export default function Dashboard() {
  const [s, setS] = useState<Summary | null>(null)
  const [accts, setAccts] = useState<AccountRow[]>([])
  const [ag, setAg] = useState<AgentsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const mounted = useRef(true)

  useEffect(() => {
    // Reset mounted flag — in Strict Mode the ref persists across mounts.
    mounted.current = true

    const fetch = () => {
      setLoading(true)
      Promise.all([
        getSummary(),
        getAccounts(5),
        getAgents(),
      ]).then(([summary, accounts, agents]) => {
        if (!mounted.current) return
        if (summary !== null) setS(summary)
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
  }, [])

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
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>Top Accounts (tokens)</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={accts}>
                <XAxis dataKey="account_id" tick={{ fontSize: 11 }} />
                <YAxis /><Tooltip />
                <Bar dataKey="tokens" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Agent Usage</CardTitle></CardHeader>
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
