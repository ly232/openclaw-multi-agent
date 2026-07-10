import { useState } from "react"
import { postQuery, QueryResult } from "../api/client"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"

const DEFAULT_SQL = "SELECT * FROM interactions ORDER BY timestamp DESC LIMIT 10"

export default function DuckDB() {
  const [sql, setSql] = useState(DEFAULT_SQL)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [running, setRunning] = useState(false)

  async function run() {
    if (!sql.trim()) return
    setRunning(true)
    try {
      const res = await postQuery(sql)
      setResult(res ?? { columns: [], rows: [], error: "No response from server" })
    } catch {
      setResult({ columns: [], rows: [], error: "Request failed" })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">DuckDB Query</h2>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">SQL</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="w-full h-32 p-3 border rounded-lg font-mono text-sm bg-gray-50 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
            value={sql}
            onChange={e => setSql(e.target.value)}
            placeholder="Enter SQL query..."
            spellCheck={false}
          />
          <button
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            onClick={run}
            disabled={running || !sql.trim()}
          >
            {running ? "Running..." : "▶ Run"}
          </button>
        </CardContent>
      </Card>

      {result?.error && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-red-600">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">
              {result.error}
            </pre>
          </CardContent>
        </Card>
      )}

      {result && !result.error && result.columns.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Results ({result.rows.length} row{result.rows.length !== 1 ? "s" : ""})
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr>
                  {result.columns.map(col => (
                    <th
                      key={col}
                      className="border border-gray-300 dark:border-gray-600 px-3 py-2 bg-gray-100 dark:bg-gray-800 text-left font-semibold whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, i) => (
                  <tr key={i} className="even:bg-gray-50 dark:even:bg-gray-800/50">
                    {row.map((val, j) => (
                      <td
                        key={j}
                        className="border border-gray-300 dark:border-gray-600 px-3 py-1.5 whitespace-nowrap max-w-md truncate"
                        title={val != null ? String(val) : ""}
                      >
                        {val != null ? String(val) : <span className="text-gray-400 italic">NULL</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {result && !result.error && result.columns.length === 0 && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm text-gray-500">Query executed successfully — no result columns.</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
