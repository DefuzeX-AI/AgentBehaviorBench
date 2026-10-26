import type { ResumeIssue } from "../types"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"
import { ArrowRight } from "../ui/icons"

const SEV: Record<string, { label: string; tone: "rose" | "amber" | "slate" }> = {
  high: { label: "高", tone: "rose" },
  medium: { label: "中", tone: "amber" },
  low: { label: "低", tone: "slate" },
}

export function IssueCard({ issue }: { issue: ResumeIssue }) {
  const sev = SEV[issue.severity] ?? SEV.low
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-1.5">
        <Badge tone={sev.tone}>嚴重度：{sev.label}</Badge>
        <span className="text-sm font-medium text-slate-500">{issue.area}</span>
      </div>
      <p className="text-sm text-slate-800">{issue.problem}</p>
      <p className="text-sm text-emerald-700 mt-1.5 flex items-start gap-1">
        <ArrowRight className="w-4 h-4 mt-0.5 shrink-0" />{issue.fix}
      </p>
    </Card>
  )
}
