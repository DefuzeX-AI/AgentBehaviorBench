import { useEffect, useRef, useState } from "react"
import type { ChangeEvent } from "react"
import type { ResumeAssessment, UserProfile, SSEEvent } from "../types"
import { readSSE } from "../sse"
import { newTaskId, stopTask } from "../lib/taskControl"
import { SAMPLE_RESUME } from "../sampleResume"
import { Dashboard } from "../components/Dashboard"
import { Card } from "../ui/Card"
import { Button } from "../ui/Button"
import { Skeleton } from "../ui/Skeleton"
import { EmptyState } from "../ui/EmptyState"
import { Gauge, Upload, Loader2, Timer, ListChecks, XCircle } from "../ui/icons"

const RESUME_HEALTH_WAIT_HINT = "深度健檢通常需要 30 秒到 2 分鐘，長履歷、PDF 格式或 CLI 模型可能更久。"
const DEEP_SAMPLE: ResumeAssessment = {
  assessment_mode: "deep",
  fallback_reason: "",
  overall_score: 86,
  clarity_score: 84,
  impact_score: 82,
  ats_keyword_score: 88,
  localization_score: 90,
  completeness_score: 86,
  summary: "這是一份深度健檢完成時的範例。報告會同時檢查定位、成果量化、ATS 關鍵字、台灣履歷慣例與可直接套用的改寫方式。",
  strengths: [
    "目標職稱明確，技能區與工作經歷能互相支撐。",
    "已有部分量化成果，可讓招募者快速判斷影響力。",
  ],
  issues: [
    {
      severity: "medium",
      area: "量化成果",
      problem: "部分經歷仍停留在職責描述，缺少規模、改善幅度或使用者影響。",
      fix: "把『負責開發 API』改成『用 FastAPI 建置付款 API，將延遲降低 42%，支援 12 萬名使用者』。",
    },
    {
      severity: "low",
      area: "ATS 關鍵字",
      problem: "技能與經歷中的關鍵字可再對齊目標職缺。",
      fix: "依目標職稱補上框架、資料庫、雲端、測試、部署與領域關鍵字。",
    },
  ],
  rewrite_examples: [
    {
      original: "負責後端 API 開發與維護。",
      improved: "使用 FastAPI / PostgreSQL 建置核心 API，將平均回應時間降低 42%，並支援每日 12 萬次請求。",
      why: "加入技術、成果與規模，讓招募者能判斷你的實際貢獻。",
    },
  ],
}

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`
}

export function ResumeHealthView(
  { onProfile }: { onProfile?: (p: UserProfile, meta?: { label?: string; resumeLabel?: string }) => void },
) {
  const [text, setText] = useState("")
  const [status, setStatus] = useState("")
  const [busy, setBusy] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [assessment, setAssessment] = useState<ResumeAssessment | null>(null)
  const [error, setError] = useState("")
  const [showSample, setShowSample] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const taskIdRef = useRef("")
  const stoppingRef = useRef(false)

  useEffect(() => {
    if (!busy) return
    const id = window.setInterval(() => setElapsedSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [busy])

  async function evaluate(form: FormData, resumeLabel: string) {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    const taskId = newTaskId("resume-health")
    abortRef.current = ctrl
    taskIdRef.current = taskId
    stoppingRef.current = false
    form.append("task_id", taskId)
    setBusy(true); setError(""); setAssessment(null)
    setElapsedSeconds(0)
    setStatus(`上傳中…${RESUME_HEALTH_WAIT_HINT}`)
    try {
      const resp = await fetch("/api/resume/evaluate", { method: "POST", body: form, signal: ctrl.signal })
      await readSSE(resp, (ev: SSEEvent) => {
        if (ev.type === "progress") setStatus(ev.message)
        else if (ev.type === "profile") {
          onProfile?.(ev.data as UserProfile, { resumeLabel })  // 本次 session 共用，跨 session 需手動儲存 Profile
        }
        else if (ev.type === "assessment") setAssessment(ev.data as ResumeAssessment)
        else if (ev.type === "stopped") { stoppingRef.current = true; setStatus(ev.message || "已停止健檢") }
        else if (ev.type === "error") setError(ev.message)
        else if (ev.type === "done") setStatus("完成")
      })
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return
      setError("連線發生問題，請確認伺服器是否啟動。")
    } finally {
      if (abortRef.current === ctrl) {
        setBusy(false)
        abortRef.current = null
        taskIdRef.current = ""
        if (stoppingRef.current) setStatus("已停止健檢")
        stoppingRef.current = false
      }
    }
  }

  async function stopEvaluate() {
    stoppingRef.current = true
    setStatus("正在停止健檢…")
    try {
      await stopTask(taskIdRef.current)
    } catch {
      // 即使停止請求失敗，仍中止目前前端串流，避免畫面卡住。
    } finally {
      abortRef.current?.abort()
      setBusy(false)
      setStatus("已停止健檢")
    }
  }

  function onSubmitText() {
    if (!text.trim()) { setError("請先貼上或載入履歷文字"); return }
    const form = new FormData()
    form.append("resume_text", text)
    evaluate(form, "貼上的履歷")
  }

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const form = new FormData()
    form.append("file", f)
    evaluate(form, f.name)
    e.target.value = ""
  }

  return (
    <div>
      <Card className="p-5 mb-6">
        <textarea
          className="w-full border border-slate-300 rounded-lg p-3 text-sm h-40 focus:outline-none focus:ring-2 focus:ring-brand-200"
          placeholder="貼上履歷文字…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex flex-wrap gap-2 mt-3 items-center">
          <Button onClick={onSubmitText} loading={busy} icon={Gauge}>開始健檢</Button>
          {busy && <Button variant="danger" onClick={stopEvaluate} icon={XCircle}>停止</Button>}
          <Button variant="secondary" onClick={() => setText(SAMPLE_RESUME)} disabled={busy}>載入範例履歷</Button>
          <Button variant="secondary" onClick={() => setShowSample((v) => !v)} disabled={busy}>
            {showSample ? "隱藏深度範例" : "查看深度健檢範例"}
          </Button>
          <label className={`inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg font-medium border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 transition cursor-pointer focus-within:ring-2 focus-within:ring-brand-300 ${busy ? "opacity-50 pointer-events-none" : ""}`}>
            <Upload className="w-4 h-4" />上傳檔案（PDF/DOCX/TXT）
            <input type="file" accept=".pdf,.docx,.txt" className="sr-only" onChange={onFile} disabled={busy} />
          </label>
          {busy && (
            <span className="text-sm text-slate-500 inline-flex items-center gap-1.5">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>{status || "準備中…"}</span>
              <span className="text-slate-400">已等待 {formatElapsed(elapsedSeconds)}</span>
            </span>
          )}
        </div>
        {error && <p className="text-sm text-rose-600 mt-2">{error}</p>}
      </Card>

      {busy && !assessment && (
        <div className="space-y-6">
          <Card className="p-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
              <div className="h-12 w-12 shrink-0 rounded-lg bg-brand-50 text-brand-700 grid place-items-center">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold text-slate-900">正在進行履歷健檢</h2>
                  <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600">
                    <Timer className="h-3.5 w-3.5" />已等待 {formatElapsed(elapsedSeconds)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-600">{status || "準備中…"}</p>
                <p className="mt-1 text-sm text-slate-500">{RESUME_HEALTH_WAIT_HINT}</p>
              </div>
              <Button variant="danger" onClick={stopEvaluate} icon={XCircle}>停止</Button>
            </div>
            <div className="mt-5 grid gap-4 border-t border-slate-200 pt-4 md:grid-cols-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <ListChecks className="h-4 w-4 text-brand-600" />解析背景
                </div>
                <p className="mt-1 text-xs text-slate-500">整理姓名、定位、技能與經歷。</p>
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Gauge className="h-4 w-4 text-brand-600" />深度評分
                </div>
                <p className="mt-1 text-xs text-slate-500">檢查 ATS、量化成果與台灣履歷慣例。</p>
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Loader2 className="h-4 w-4 text-brand-600" />整理報告
                </div>
                <p className="mt-1 text-xs text-slate-500">產出問題清單與改寫範例。</p>
              </div>
            </div>
            <div className="mt-5 space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-4/5" />
            </div>
          </Card>
        </div>
      )}

      {!busy && showSample && (
        <section className="mb-6">
          <div className="mb-2">
            <p className="text-sm font-medium text-slate-700">深度健檢範例</p>
            <p className="text-xs text-slate-500">這不是你的履歷結果，只用來展示正常深度健檢完成時的報告樣式。</p>
          </div>
          <Dashboard a={DEEP_SAMPLE} />
        </section>
      )}

      {!busy && !assessment && !error && !showSample && (
        <Card className="p-2">
          <EmptyState
            icon={Gauge}
            title="貼上或上傳你的履歷，開始健檢"
            desc="AI 會評分表達清晰度、量化成果、ATS 關鍵字與台灣慣例，並給出可改進項目與改寫範例。"
          />
        </Card>
      )}

      {assessment && <Dashboard a={assessment} />}
    </div>
  )
}
