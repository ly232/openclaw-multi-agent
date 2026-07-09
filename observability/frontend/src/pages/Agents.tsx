import { useEffect, useState } from "react"
import { getAgents, AgentsResponse, getAgentInteractions, MsgRow } from "../api/client"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { formatTokens } from "../lib/utils"

export default function Agents() {
  const [data, setData] = useState<AgentsResponse | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<MsgRow[]>([])

  useEffect(() => { getAgents().then(setData) }, [])
  useEffect(() => {
    if (selected) getAgentInteractions(selected, 10).then(setMsgs)
  }, [selected])

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Agents</h2>
      <div className="grid grid-cols-2 gap-4">
        {data?.metrics?.map(m => (
          <Card key={m.agent}>
            <CardHeader><CardTitle>{m.agent}</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div><span className="text-gray-500">Requests</span><p className="font-bold">{m.requests}</p></div>
                <div><span className="text-gray-500">Avg Tokens</span><p className="font-bold">{formatTokens(m.avg_tokens)}</p></div>
                <div><span className="text-gray-500">Avg Latency</span><p className="font-bold">{m.avg_latency_ms}ms</p></div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader><CardTitle>All Agents</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left">
              <th className="pb-2 font-medium">Agent</th>
              <th className="pb-2 font-medium">Requests</th>
              <th className="pb-2 font-medium">Tokens</th>
              <th className="pb-2 font-medium">Avg Latency</th>
            </tr></thead>
            <tbody>{data?.agents?.map(a => (
              <tr key={a.agent} className="border-b hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                  onClick={() => setSelected(a.agent)}>
                <td className="py-2">{a.agent}</td>
                <td className="py-2">{a.requests}</td>
                <td className="py-2">{formatTokens(a.tokens)}</td>
                <td className="py-2">{a.avg_latency_ms}ms</td>
              </tr>
            ))}</tbody>
          </table>
        </CardContent>
      </Card>
      {selected && (
        <Card>
          <CardHeader><CardTitle>Interactions — {selected}</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left">
                <th className="pb-2 font-medium">Time</th>
                <th className="pb-2 font-medium">Account</th>
                <th className="pb-2 font-medium">Task</th>
                <th className="pb-2 font-medium">Tokens</th>
              </tr></thead>
              <tbody>{msgs.map((m, i) => (
                <tr key={i} className="border-b">
                  <td className="py-2">{new Date(m.timestamp).toLocaleTimeString()}</td>
                  <td className="py-2">{m.account_id ?? "-"}</td>
                  <td className="py-2 truncate max-w-xs">{m.task}</td>
                  <td className="py-2">{m.tokens}</td>
                </tr>
              ))}</tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
