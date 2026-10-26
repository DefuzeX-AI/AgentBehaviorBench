import { useEffect, useState } from "react"
import type { MouseEvent } from "react"
import type { ResumeCheckDetail, ResumeCheckSummary, UserProfile } from "../types"
import { Dashboard } from "../components/Dashboard"
import { Card } from "../ui/Card"
import { EmptyState } from "../ui/EmptyState"
import { Badge } from "../ui/Badge"
import { ArrowLeft, FileChartColumn, Trash2, UserRound } from "../ui/icons"

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" }) }
  catch { return iso }
}

function modeLabel(mode: string) {
  return mode === "fallback" ? "備援" : "深度"
}

export function ResumeCheckHistoryView(
  { active, onProfile }:
  { active: boolean; onProfile?: (p: UserProfile, meta?: { label?: string; resumeLabel?: string }) => void },
) {
  const [list, setList] = useState<ResumeCheckSummary[]>([])
  const [detail, setDetail] = useState<ResumeCheckDetail | null>(null)
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try { setList((await (await fetch("/api/resume/checks")).json()).checks || []) }
    catch { /* ignore transient refresh failures */ }
  }

  // active tab 才讀取後端紀錄；refresh 會在 await API 後 setState。
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (active) refresh() }, [active])

  async function open(id: number) {
    setBusy(true)
    try { setDetail(await (await fetch(`/api/resume/checks/${id}`)).json()) }
    finally { setBusy(false) }
  }

  async function del(id: number, e: MouseEvent) {
    e.stopPropagation()
    await fetch(`/api/resume/checks/${id}`, { method: "DELETE" })
    if (detail?.id === id) setDetail(null)
    refresh()
  }

  if (detail) {
    return (
      <div>
        <button onClick={() => setDetail(null)}
          className="text-sm text-brand-600 hover:text-brand-700 mb-3 inline-flex items-center gap-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300 rounded">
          <ArrowLeft className="w-4 h-4" />回到健檢紀錄
        </button>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold text-slate-900">{detail.label}</h2>
              <Badge tone={detail.assessment_mode === "fallback" ? "amber" : "emerald"}>
                {modeLabel(detail.assessment_mode)}
              </Badge>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              {fmtDate(detail.created_at)}・{detail.resume_label || "履歷"}
            </p>
          </div>
          {detail.profile && (
            <button type="button"
              onClick={() => onProfile?.(detail.profile as UserProfile, {
                label: detail.candidate_name || detail.label,
                resumeLabel: detail.resume_label || "健檢紀錄",
              })}
              className="inline-flex items-center gap-1.5 text-sm border border-slate-300 rounded-lg px-3 py-1.5 text-slate-600 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300">
              <UserRound className="w-4 h-4" />套用 Profile
            </button>
          )}
        </div>
        {detail.assessment_mode === "fallback" && detail.fallback_reason && (
          <p className="mb-4 text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
            深度健檢未完成原因：{detail.fallback_reason}
          </p>
        )}
        <Dashboard a={detail.assessment} />
      </div>
    )
  }

  if (!list.length) {
    return (
      <Card className="p-2">
        <EmptyState
          icon={FileChartColumn}
          title="尚無健檢紀錄"
          desc="完成履歷健檢後，結果會自動儲存在這裡，方便比較不同履歷版本。"
        />
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <h2 className="font-semibold">健檢紀錄（{list.length}）</h2>
      {list.map((item) => (
        <Card key={item.id} interactive className="p-4 flex items-center gap-4 cursor-pointer" onClick={() => open(item.id)}>
          <div className="shrink-0 w-12 h-12 rounded-xl grid place-items-center bg-brand-50 text-brand-600">
            <FileChartColumn className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-slate-900 truncate">{item.label}</p>
              <Badge tone={item.assessment_mode === "fallback" ? "amber" : "emerald"}>
                {modeLabel(item.assessment_mode)}
              </Badge>
            </div>
            <p className="text-sm text-slate-600 truncate">
              總分 {item.overall_score}・{fmtDate(item.created_at)}
            </p>
            {item.assessment_mode === "fallback" && item.fallback_reason && (
              <p className="text-xs text-amber-700 truncate mt-0.5">原因：{item.fallback_reason}</p>
            )}
          </div>
          <button onClick={(e) => del(item.id, e)} aria-label={`刪除 ${item.label}`} title="刪除"
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation() }}
            className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300">
            <Trash2 className="w-4 h-4" />
          </button>
        </Card>
      ))}
      {busy && <p className="text-sm text-slate-400">載入中…</p>}
    </div>
  )
}
