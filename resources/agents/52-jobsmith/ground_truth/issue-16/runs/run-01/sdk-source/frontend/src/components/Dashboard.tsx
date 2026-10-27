import type { ResumeAssessment } from "../types"
import { ScoreRing } from "./ScoreRing"
import { ScoreBars } from "./ScoreBars"
import { IssueCard } from "./IssueCard"
import { RewriteCard } from "./RewriteCard"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"
import { CheckCircle2, AlertTriangle, Wand2 } from "../ui/icons"

export function Dashboard({ a }: { a: ResumeAssessment }) {
  const isFallback = a.assessment_mode === "fallback"
  return (
    <div className="space-y-6 animate-fade-in-up">
      <Card className="grid md:grid-cols-2 gap-6 items-center p-6">
        <div className="flex items-center gap-6">
          <ScoreRing score={a.overall_score} size={120} />
          <div>
            <div className="mb-2">
              <Badge tone={isFallback ? "amber" : "emerald"}>
                {isFallback ? "已改用強化備援健檢" : "深度健檢完成"}
              </Badge>
            </div>
            <h2 className="text-lg font-bold mb-1">履歷健檢總分</h2>
            <p className="text-sm text-slate-600">{a.summary}</p>
            {isFallback && a.fallback_reason && (
              <p className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1.5">
                深度健檢未完成原因：{a.fallback_reason}
              </p>
            )}
          </div>
        </div>
        <ScoreBars scores={a as unknown as Record<string, number>} />
      </Card>

      {a.strengths.length > 0 && (
        <section>
          <h3 className="font-semibold mb-2 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />優點
          </h3>
          <div className="grid md:grid-cols-2 gap-2">
            {a.strengths.map((s, i) => (
              <div key={i} className="text-sm bg-emerald-50 border border-emerald-100 rounded-lg p-3 text-slate-700">{s}</div>
            ))}
          </div>
        </section>
      )}

      {a.issues.length > 0 && (
        <section>
          <h3 className="font-semibold mb-2 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />可改進項目
          </h3>
          <div className="grid md:grid-cols-2 gap-3">
            {a.issues.map((it, i) => <IssueCard key={i} issue={it} />)}
          </div>
        </section>
      )}

      {a.rewrite_examples.length > 0 && (
        <section>
          <h3 className="font-semibold mb-2 flex items-center gap-2">
            <Wand2 className="w-4 h-4 text-brand-600" />改寫範例
          </h3>
          <div className="grid md:grid-cols-2 gap-3">
            {a.rewrite_examples.map((rw, i) => <RewriteCard key={i} rw={rw} />)}
          </div>
        </section>
      )}
    </div>
  )
}
