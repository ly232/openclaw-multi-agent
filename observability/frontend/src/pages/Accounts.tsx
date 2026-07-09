import { useEffect, useState } from "react"
import { getAccounts, AccountRow, getAccountMessages, MsgRow } from "../api/client"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { formatTokens, formatCost } from "../lib/utils"

export default function Accounts() {
  const [accounts, setAccounts] = useState<AccountRow[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<MsgRow[]>([])
  const [limit] = useState(10)

  useEffect(() => { getAccounts(limit).then(setAccounts) }, [limit])
  useEffect(() => {
    if (selected) getAccountMessages(selected, 10).then(setMsgs)
  }, [selected])

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Accounts</h2>
      <Card>
        <CardHeader><CardTitle>Top Accounts</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left">
              <th className="pb-2 font-medium">Account</th>
              <th className="pb-2 font-medium">Messages</th>
              <th className="pb-2 font-medium">Tokens</th>
              <th className="pb-2 font-medium">Cost</th>
            </tr></thead>
            <tbody>{accounts.map(a => (
              <tr key={a.account_id} className="border-b hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                  onClick={() => setSelected(a.account_id)}>
                <td className="py-2">{a.account_id}</td>
                <td className="py-2">{a.messages}</td>
                <td className="py-2">{formatTokens(a.tokens)}</td>
                <td className="py-2">{formatCost(a.cost)}</td>
              </tr>
            ))}</tbody>
          </table>
        </CardContent>
      </Card>
      {selected && (
        <Card>
          <CardHeader><CardTitle>Messages — {selected}</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left">
                <th className="pb-2 font-medium">Time</th>
                <th className="pb-2 font-medium">Message</th>
                <th className="pb-2 font-medium">Agent</th>
                <th className="pb-2 font-medium">Tokens</th>
              </tr></thead>
              <tbody>{msgs.map((m, i) => (
                <tr key={i} className="border-b">
                  <td className="py-2">{new Date(m.timestamp).toLocaleTimeString()}</td>
                  <td className="py-2 truncate max-w-xs">{m.user_message}</td>
                  <td className="py-2">{m.agent}</td>
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
