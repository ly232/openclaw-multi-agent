import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { getMessage, getTrace, Interaction, TraceEvent, postEvaluation } from "../api/client"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { formatTokens } from "../lib/utils"

export default function Messages() {
  const { id } = useParams()
  const [msg, setMsg] = useState<Interaction | null>(null)
  const [trace, setTrace] = useState<TraceEvent[]>([])
  const [scores, setScores] = useState({ correctness: 5, relevance: 5, completeness: 5, clarity: 5 })
  const [evalResult, setEvalResult] = useState<string | null>(null)

  useEffect(() => {
    if (id) { getMessage(id).then(setMsg); getTrace(id).then(setTrace) }
  }, [id])

  const handleEval = async () => {
    if (!msg) return
    const overall = (scores.correctness + scores.relevance + scores.completeness + scores.clarity) / 4
    await postEvaluation(msg.interaction_id, { ...scores, overall })
    setEvalResult("Saved ✓")
  }

  if (!id) return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Messages</h2>
      <p className="text-gray-500">Click a message from Accounts or Agents to view details.</p>
    </div>
  )

  return (
    <div className="space-y-6 max-w-4xl">
      <Link to="/messages" className="text-sm text-blue-600 hover:underline">&larr; Back</Link>
      <h2 className="text-2xl font-bold">Message Detail</h2>
      {msg && (
        <>
          <div className="grid grid-cols-4 gap-4 text-sm">
            <div><span className="text-gray-500">Account</span><p className="font-medium">{msg.account_id}</p></div>
            <div><span className="text-gray-500">Agent</span><p className="font-medium">{msg.root_agent}</p></div>
            <div><span className="text-gray-500">Tokens</span><p className="font-medium">{formatTokens(msg.total_tokens)}</p></div>
            <div><span className="text-gray-500">Latency</span><p className="font-medium">{msg.latency_ms}ms</p></div>
          </div>
          <Card><CardHeader><CardTitle>User Message</CardTitle></CardHeader>
            <CardContent><p className="text-sm whitespace-pre-wrap">{msg.user_message}</p></CardContent>
          </Card>
          <Card><CardHeader><CardTitle>Assistant Response</CardTitle></CardHeader>
            <CardContent><p className="text-sm whitespace-pre-wrap">{msg.assistant_response}</p></CardContent>
          </Card>
          {trace.length > 0 && (
            <Card><CardHeader><CardTitle>Execution Trace</CardTitle></CardHeader>
              <CardContent>
                <div className="relative pl-6 border-l-2 border-gray-200 space-y-3">
                  {trace.map((ev, i) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-[25px] w-3 h-3 rounded-full bg-blue-500 border-2 border-white dark:border-gray-950" />
                      <div className="text-xs text-gray-500">{new Date(ev.ts).toISOString().slice(11, 19)}</div>
                      <div className="text-sm font-medium">{ev.agent}</div>
                      <div className="text-xs text-gray-600">{ev.event_type}</div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
          <Card><CardHeader><CardTitle>Quick Evaluation</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 gap-4">
                {(["correctness", "relevance", "completeness", "clarity"] as const).map(k => (
                  <div key={k}>
                    <label className="text-xs capitalize">{k}</label>
                    <select className="w-full border rounded p-1 text-sm"
                      value={scores[k]}
                      onChange={e => setScores(s => ({ ...s, [k]: Number(e.target.value) }))}
                    >{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}</select>
                  </div>
                ))}
              </div>
              <button onClick={handleEval}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
              >Save Evaluation</button>
              {evalResult && <span className="ml-3 text-green-600 text-sm">{evalResult}</span>}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
