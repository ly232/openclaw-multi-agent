import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"

export default function Evaluations() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Evaluations</h2>
      <p className="text-gray-500">Quality evaluation dashboard — coming in Phase 2.</p>
      <Card>
        <CardHeader><CardTitle>LLM Auto-Rater</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600">
            Click "Evaluate Response" on any Message detail page to rate correctness, relevance,
            completeness, and clarity. Scores are stored in DuckDB and will be aggregated here.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
