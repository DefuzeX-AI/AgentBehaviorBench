import { useEffect, useRef, useState } from "react"
import type { MouseEvent } from "react"
import type { UserProfile, PipelineState } from "../types"
import { Card } from "../ui/Card"
import { Button } from "../ui/Button"
import { Badge } from "../ui/Badge"
import { EmptyState } from "../ui/EmptyState"
import {
  MatchCard, CompanyCard, ResumeDoc, CoverLetterDoc, InterviewKitDoc, CritiqueCard,
} from "../components/pipeline/Documents"
import {
  Archive, Trash2, ArrowLeft, FileDown, Printer, Workflow, MessagesSquare, CircleCheck, Loader2,
  AlertTriangle, XCircle,
} from "../ui/icons"

interface PkgSummary {
  id: number; created_at: string; job_title: string; company: string
  match_score: number; approved: number; status?: string; thread_id?: string; has_artifacts?: number
}
type PackagePayload = PipelineState & { error?: { message?: string } }
interface PackageDetail {
  id: number; package: PackagePayload; jd_text?: string; profile?: UserProfile | null
  approved?: number; status?: string; has_artifacts?: number
}

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" }) }
  catch { return iso }
}

function hasArtifacts(pkg: PipelineState | null | undefined) {
  return Boolean(pkg?.tailored_resume || pkg?.cover_letter || pkg?.interview_kit)
}

function statusBadge(p: PkgSummary) {
  if (p.status === "running") return <Badge tone="brand">進行中 · 點開看進度</Badge>
  if (p.status === "failed") return <Badge tone="rose">產生失敗</Badge>
  if (p.status === "stopped" || p.has_artifacts === 0) return <Badge tone="slate">未產出</Badge>
  if (p.approved) return <Badge tone="emerald">已核可</Badge>
  return <Badge tone="amber">待審</Badge>
}

export function HistoryView(
  { active, onReopen, onInterview, onWatch }:
  {
    active: boolean
    onReopen: (jd: string, profile?: UserProfile | null) => void
    onInterview: (jd: string, profile?: UserProfile | null) => void
    onWatch?: (threadId: string, packageId: number, title: string) => void
  },
) {
  const [list, setList] = useState<PkgSummary[]>([])
  const [detail, setDetail] = useState<PackageDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const pollTimer = useRef<number | null>(null)

  async function refresh() {
    try {
      const d = await (await fetch("/api/history")).json()
      const pkgs: PkgSummary[] = d.packages || []
      setList(pkgs)
      // 有「進行中」就定期重抓，讓 進行中 → 待審 自動更新。
      if (pollTimer.current) { window.clearTimeout(pollTimer.current); pollTimer.current = null }
      if (active && pkgs.some((p) => p.status === "running")) {
        pollTimer.current = window.setTimeout(refresh, 2000)
      }
    } catch { /* 靜默 */ }
  }
  // 切到此分頁（active）時載入清單；資料載入是 effect 的正當用途。
  useEffect(() => {
    if (active) refresh()
    return () => { if (pollTimer.current) window.clearTimeout(pollTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

  async function open(id: number) {
    setBusy(true)
    try { setDetail(await (await fetch(`/api/history/${id}`)).json()) }
    finally { setBusy(false) }
  }

  async function del(id: number, e: MouseEvent) {
    e.stopPropagation()
    await fetch(`/api/history/${id}`, { method: "DELETE" })
    if (detail?.id === id) setDetail(null)
    refresh()
  }

  // 核可：把待審投遞包標記為已核可（批次產生的包在此逐一審核）。
  async function approve(id: number, e?: MouseEvent) {
    e?.stopPropagation()
    await fetch(`/api/history/${id}/approve`, { method: "POST" })
    if (detail?.id === id) setDetail({ ...detail, approved: 1 })
    refresh()
  }

  async function downloadDocx(pkg: PipelineState) {
    const r = pkg.tailored_resume, c = pkg.cover_letter, k = pkg.interview_kit
    const body = {
      job_title: pkg.parsed_job?.title || "求職投遞包",
      company: pkg.parsed_job?.company || pkg.company_brief?.company || "",
      resume: r ? { summary: r.summary, bullets: r.bullets, ats_keywords_hit: r.ats_keywords_hit } : undefined,
      cover_letter: c ? { subject: c.subject, body: c.body } : undefined,
      interview: k || undefined,
    }
    const resp = await fetch("/api/export/docx", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    })
    if (!resp.ok) return
    const blob = await resp.blob()
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob); a.download = "投遞包.docx"; a.click(); URL.revokeObjectURL(a.href)
  }

  // ---- 詳情檢視 ----
  if (detail) {
    const p = detail.package || {}
    const hasDocs = hasArtifacts(p)
    const canReview = detail.status === "done" && hasDocs
    const failed = detail.status === "failed"
    const stopped = detail.status === "stopped" || !hasDocs
    const emptyTitle = failed ? "產生失敗" : "未產出可審核文件"
    const emptyDesc = failed
      ? (p.error?.message || "背景產生過程中斷，這筆紀錄沒有可顯示的投遞包內容。")
      : "這筆流程已結束，但沒有產出客製履歷、求職信或面試準備；通常是適配度過低或流程在產出前停止。"
    return (
      <div>
        <button onClick={() => setDetail(null)}
          className="no-print text-sm text-brand-600 hover:text-brand-700 mb-3 inline-flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" />回列表
        </button>
        <div className="no-print flex flex-wrap gap-2 mb-4">
          {canReview && detail.approved !== 1 && (
            <Button variant="primary" icon={CircleCheck} onClick={() => approve(detail.id)}>核可</Button>
          )}
          <Button variant="secondary" icon={Workflow}
            onClick={() => onReopen(detail.jd_text || "", detail.profile ?? null)}>重新開啟到工作台</Button>
          <Button variant="secondary" icon={MessagesSquare}
            onClick={() => onInterview(detail.jd_text || "", detail.profile ?? null)}>用這份做面試模擬</Button>
          {hasDocs && <Button variant="secondary" icon={FileDown} onClick={() => downloadDocx(p)}>下載 Word</Button>}
          {hasDocs && <Button variant="secondary" icon={Printer} onClick={() => window.print()}>列印 / 匯出 PDF</Button>}
        </div>
        <div className="space-y-4">
          {stopped && (
            <Card className="p-2">
              <EmptyState icon={failed ? XCircle : AlertTriangle} title={emptyTitle} desc={emptyDesc} />
            </Card>
          )}
          {p.match_report && <MatchCard m={p.match_report} />}
          {p.company_brief && <CompanyCard c={p.company_brief} />}
          {p.tailored_resume && <ResumeDoc r={p.tailored_resume} />}
          {p.cover_letter && <CoverLetterDoc c={p.cover_letter} />}
          {p.interview_kit && <InterviewKitDoc k={p.interview_kit} />}
          {p.critique && <CritiqueCard q={p.critique} />}
        </div>
      </div>
    )
  }

  // ---- 清單 ----
  if (!list.length) {
    return (
      <Card className="p-2">
        <EmptyState icon={Archive} title="還沒有投遞包紀錄"
          desc="到「投遞包工作台」跑完一份投遞包後，會自動存到這裡，可回查、重新開啟、下載。" />
      </Card>
    )
  }
  return (
    <div className="space-y-3">
      <h2 className="font-semibold">我的投遞包（{list.length}）</h2>
      {list.map((p) => {
        const running = p.status === "running"
        const failed = p.status === "failed"
        const stopped = p.status === "stopped" || p.has_artifacts === 0
        const reviewable = p.status === "done" && p.has_artifacts !== 0 && !p.approved
        const onCard = () => {
          if (running) { if (p.thread_id && onWatch) onWatch(p.thread_id, p.id, p.job_title) }
          else open(p.id)
        }
        return (
          <Card key={p.id} interactive className="p-4 flex items-center gap-4 cursor-pointer"
            onClick={onCard}>
            <div className={`shrink-0 w-12 h-12 rounded-xl grid place-items-center font-bold text-white ${
              running ? "bg-slate-300"
                : failed ? "bg-rose-500"
                  : stopped ? "bg-slate-400"
                : p.match_score >= 80 ? "bg-emerald-600" : p.match_score >= 60 ? "bg-amber-500" : "bg-slate-400"}`}>
              {running ? <Loader2 className="w-5 h-5 animate-spin" />
                : failed ? <XCircle className="w-5 h-5" />
                  : stopped ? <AlertTriangle className="w-5 h-5" />
                    : p.match_score}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-slate-900 truncate">{p.job_title}</p>
              <p className="text-sm text-slate-600 truncate flex items-center gap-2">
                <span className="truncate">{p.company || "—"} · {fmtDate(p.created_at)}</span>
                {statusBadge(p)}
              </p>
            </div>
            {reviewable && (
              <button onClick={(e) => approve(p.id, e)} aria-label={`核可 ${p.job_title}`} title="核可"
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation() }}
                className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300">
                <CircleCheck className="w-4 h-4" />
              </button>
            )}
            <button onClick={(e) => del(p.id, e)} aria-label={`刪除 ${p.job_title}`} title="刪除"
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation() }}
              className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300">
              <Trash2 className="w-4 h-4" />
            </button>
          </Card>
        )
      })}
      {busy && <p className="text-sm text-slate-400">載入中…</p>}
    </div>
  )
}
