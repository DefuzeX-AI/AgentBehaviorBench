import { useEffect, useRef, useState } from "react"
import type { CandidateProfile, UserProfile, InterviewQuestion, AnswerFeedback, InterviewSummary, Seed } from "../types"
import { profileDisplayName } from "../lib/profiles"
import { newTaskId, stopTask } from "../lib/taskControl"
import { Card } from "../ui/Card"
import { Button } from "../ui/Button"
import { Badge } from "../ui/Badge"
import { EmptyState } from "../ui/EmptyState"
import { ScoreRing } from "../components/ScoreRing"
import {
  MessagesSquare, CheckCircle2, AlertTriangle, RefreshCw, ArrowRight, Archive, Loader2, X,
  UserRound, XCircle,
} from "../ui/icons"

interface PkgPick {
  id: number; job_title: string; company: string; match_score: number; status?: string
}

// 每個職缺一個獨立的面試對話 session，切換不會互相覆蓋。
interface Session {
  key: string
  title: string
  jd: string
  profile: UserProfile | null
  loading: boolean   // 出題中
  busy: boolean      // 送出/評分/總評中
  error: string
  questions: InterviewQuestion[]
  idx: number
  answer: string
  feedback: AnswerFeedback | null
  transcript: { question: string; answer: string; score: number }[]
  summary: InterviewSummary | null
}

function newSession(key: string, title: string, jd = "", profile: UserProfile | null = null): Session {
  return {
    key, title, jd, profile, loading: true, busy: false, error: "",
    questions: [], idx: 0, answer: "", feedback: null, transcript: [], summary: null,
  }
}

const jdTitle = (jd: string) =>
  jd.split("\n").map((s) => s.trim()).find(Boolean)?.slice(0, 24) || "面試"

export function InterviewView(
  { active, activeProfile, seed }:
  { active?: boolean; activeProfile?: CandidateProfile | null; seed?: Seed | null },
) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentKey, setCurrentKey] = useState<string | null>(null)
  const [packages, setPackages] = useState<PkgPick[]>([])
  const [manualJd, setManualJd] = useState("")
  const taskRefs = useRef<Record<string, { taskId: string; ctrl: AbortController }>>({})

  const cur = sessions.find((s) => s.key === currentKey) || null
  const patch = (key: string, p: Partial<Session>) =>
    setSessions((ss) => ss.map((s) => (s.key === key ? { ...s, ...p } : s)))

  function startTask(key: string, prefix: string) {
    const previous = taskRefs.current[key]
    if (previous) {
      void stopTask(previous.taskId).catch(() => undefined)
      previous.ctrl.abort()
    }
    const ctrl = new AbortController()
    const taskId = newTaskId(`${prefix}-${key.replace(/[^a-zA-Z0-9_-]/g, "")}`)
    taskRefs.current[key] = { taskId, ctrl }
    return { taskId, ctrl }
  }

  function finishTask(key: string, ctrl: AbortController) {
    if (taskRefs.current[key]?.ctrl === ctrl) delete taskRefs.current[key]
  }

  async function stopSessionTask(key: string) {
    const current = taskRefs.current[key]
    if (!current) return
    try {
      await stopTask(current.taskId)
    } catch {
      // 停止端點失敗時仍中止前端等待。
    } finally {
      current.ctrl.abort()
      delete taskRefs.current[key]
      patch(key, { loading: false, busy: false, error: "已停止任務" })
    }
  }

  async function loadPackages() {
    try {
      const d = await (await fetch("/api/history")).json()
      setPackages(((d.packages || []) as PkgPick[]).filter((p) => p.status !== "running"))
    } catch { /* 靜默 */ }
  }

  // 依某份 JD 出題（建立/重啟 session 的核心）。
  async function beginQuestions(key: string, jd: string, profile: UserProfile | null) {
    patch(key, {
      loading: true, error: "", jd, profile,
      questions: [], idx: 0, answer: "", feedback: null, transcript: [], summary: null,
    })
    const { taskId, ctrl } = startTask(key, "interview-start")
    try {
      const r = await fetch("/api/interview/start", {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({ jd_text: jd, profile, task_id: taskId }),
      })
      const d = await r.json()
      if (!r.ok) { patch(key, { loading: false, error: d.error || "啟動失敗" }); return }
      const qs: InterviewQuestion[] = d.questions || []
      if (!qs.length) { patch(key, { loading: false, error: "AI 暫時無法出題，請稍後再試或換一份 JD。" }); return }
      patch(key, { loading: false, questions: qs })
    } catch (e) {
      if ((e as Error)?.name === "AbortError") {
        patch(key, { loading: false, error: "已停止任務" })
        return
      }
      patch(key, { loading: false, error: "連線發生問題，請確認伺服器是否啟動。" })
    } finally {
      finishTask(key, ctrl)
    }
  }

  // 用已知 JD 開一個新 session（手動貼 JD / 從「我的投遞包」帶入）。
  async function startSession(key: string, title: string, jd: string, profile: UserProfile | null) {
    if (!jd.trim()) return
    if (sessions.some((s) => s.key === key)) { setCurrentKey(key); return }  // 已有 → 切過去
    setSessions((ss) => [...ss, newSession(key, title, jd, profile)])
    setCurrentKey(key)
    await beginQuestions(key, jd, profile)
  }

  // 從「我的投遞包」選一筆：先建 session（立即顯示出題中，避免「沒反應」），再抓 JD 出題。
  async function startPackageSession(p: PkgPick) {
    const key = "pkg-" + p.id
    if (sessions.some((s) => s.key === key)) { setCurrentKey(key); return }
    const title = p.company ? `${p.company}｜${p.job_title}` : p.job_title
    setSessions((ss) => [...ss, newSession(key, title)])
    setCurrentKey(key)
    try {
      const d = await (await fetch(`/api/history/${p.id}`)).json()
      if (!d.jd_text) { patch(key, { loading: false, error: "這筆投遞包沒有可用的 JD。" }); return }
      await beginQuestions(key, d.jd_text, d.profile ?? activeProfile?.profile ?? null)
    } catch {
      patch(key, { loading: false, error: "載入投遞包失敗，請稍後再試。" })
    }
  }

  function closeSession(key: string) {
    void stopSessionTask(key)
    setSessions((ss) => ss.filter((s) => s.key !== key))
    if (currentKey === key) setCurrentKey(null)
  }

  async function loadSample() {
    const j = await (await fetch("/api/sample")).json()
    setManualJd(j.jd_text)
  }

  function setAnswer(v: string) { if (cur) patch(cur.key, { answer: v }) }

  async function submitAnswer() {
    if (!cur || !cur.answer.trim() || cur.busy) return
    const key = cur.key
    patch(key, { busy: true, error: "" })
    const { taskId, ctrl } = startTask(key, "interview-answer")
    try {
      const q = cur.questions[cur.idx]
      const r = await fetch("/api/interview/answer", {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          jd_text: cur.jd, question: q.question, answer: cur.answer,
          profile: cur.profile, task_id: taskId,
        }),
      })
      const d = await r.json()
      if (!r.ok) { patch(key, { busy: false, error: d.error || "評分失敗" }); return }
      patch(key, {
        busy: false, feedback: d as AnswerFeedback,
        transcript: [...cur.transcript, { question: q.question, answer: cur.answer, score: (d as AnswerFeedback).score }],
      })
    } catch (e) {
      if ((e as Error)?.name === "AbortError") {
        patch(key, { busy: false, error: "已停止任務" })
        return
      }
      patch(key, { busy: false, error: "連線發生問題。" })
    } finally {
      finishTask(key, ctrl)
    }
  }

  async function next() {
    if (!cur) return
    const key = cur.key
    if (cur.idx < cur.questions.length - 1) {
      patch(key, { idx: cur.idx + 1, answer: "", feedback: null }); return
    }
    patch(key, { busy: true, error: "" })
    const { taskId, ctrl } = startTask(key, "interview-summary")
    try {
      const r = await fetch("/api/interview/summary", {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          jd_text: cur.jd,
          transcript: cur.transcript.map((t) => ({ question: t.question, answer: t.answer })),
          task_id: taskId,
        }),
      })
      const d = await r.json()
      if (!r.ok) { patch(key, { busy: false, error: d.error || "總評失敗" }); return }
      patch(key, { busy: false, summary: d as InterviewSummary })
    } catch (e) {
      if ((e as Error)?.name === "AbortError") {
        patch(key, { busy: false, error: "已停止任務" })
        return
      }
      patch(key, { busy: false, error: "連線發生問題。" })
    } finally {
      finishTask(key, ctrl)
    }
  }

  // 從「我的投遞包」用該份 JD + 履歷直接開面試（由 seed.nonce 外部訊號觸發）。
  useEffect(() => {
    if (!seed?.jd) return
    const timer = window.setTimeout(() => {
      void startSession("seed-" + seed.nonce, jdTitle(seed.jd), seed.jd, seed.profile ?? activeProfile?.profile ?? null)
    }, 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce])

  // 切到此分頁、且在挑選畫面時載入「我的投遞包」清單。
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (active && currentKey === null) loadPackages()
  }, [active, currentKey])

  const tabs = sessions.length > 0 && (
    <div className="flex flex-wrap items-center gap-1.5 mb-4">
      {sessions.map((s) => (
        <div key={s.key}
          className={`inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1.5 rounded-lg text-sm border ${
            s.key === currentKey ? "bg-brand-600 text-white border-brand-600"
              : "bg-white border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
          <button onClick={() => setCurrentKey(s.key)} className="truncate max-w-[10rem]">{s.title}</button>
          {s.loading ? <Loader2 className="w-3 h-3 animate-spin" />
            : s.summary ? <CheckCircle2 className="w-3 h-3" /> : null}
          <button onClick={() => closeSession(s.key)} aria-label={`關閉 ${s.title}`}
            className="rounded hover:bg-black/10 p-0.5"><X className="w-3 h-3" /></button>
        </div>
      ))}
      <button onClick={() => setCurrentKey(null)}
        className="px-3 py-1.5 rounded-lg text-sm border border-dashed border-slate-300 text-slate-500 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300">
        ＋ 新面試
      </button>
    </div>
  )

  // ---- 挑選畫面（沒有選定 session）----
  if (!cur) {
    return (
      <div className="space-y-5">
        {tabs}
        {packages.length > 0 && (
          <Card className="p-5">
            <h3 className="font-semibold mb-1 flex items-center gap-2">
              <Archive className="w-4 h-4 text-brand-600" />用「我的投遞包」開始模擬
            </h3>
            <p className="text-sm text-slate-500 mb-3">選一筆投遞包，用它的 JD 與履歷開一個獨立的面試對話。</p>
            <div className="space-y-2 max-h-72 overflow-auto">
              {packages.map((p) => (
                <button key={p.id} onClick={() => startPackageSession(p)}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border border-slate-200 hover:border-brand-300 hover:bg-brand-50/40 transition text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300">
                  <div className={`shrink-0 w-10 h-10 rounded-lg grid place-items-center font-bold text-white text-sm ${
                    p.match_score >= 80 ? "bg-emerald-600" : p.match_score >= 60 ? "bg-amber-500" : "bg-slate-400"}`}>
                    {p.match_score}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-slate-800 truncate">{p.job_title}</p>
                    <p className="text-xs text-slate-500 truncate">{p.company || "—"}</p>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-400 ml-auto shrink-0" />
                </button>
              ))}
            </div>
          </Card>
        )}
        <Card className="p-5">
          <p className="text-sm text-slate-600 mb-2">
            {packages.length > 0 ? "或貼上" : "貼上"}目標職缺 JD，AI 面試官會依你的履歷出題、逐題給回饋與評分。
          </p>
          <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 flex items-center gap-2">
            <UserRound className="w-4 h-4 text-slate-400 shrink-0" />
            {activeProfile
              ? <>目前使用 Profile：<span className="font-medium text-slate-800">{profileDisplayName(activeProfile.profile)}</span></>
              : "目前未選 Profile；開始後會使用範例背景示意。"}
          </div>
          <textarea
            className="w-full border border-slate-300 rounded-lg p-3 text-sm h-32 focus:outline-none focus:ring-2 focus:ring-brand-200"
            placeholder="貼上職缺 JD 文字…" value={manualJd} onChange={(e) => setManualJd(e.target.value)} />
          <div className="flex flex-wrap gap-2 mt-3">
            <Button icon={MessagesSquare} disabled={!manualJd.trim()}
              onClick={() => { startSession("manual-" + Date.now(), jdTitle(manualJd), manualJd, activeProfile?.profile ?? null); setManualJd("") }}>
              開始面試
            </Button>
            <Button variant="secondary" onClick={loadSample}>載入範例 JD</Button>
          </div>
        </Card>
        {!activeProfile && packages.length === 0 && sessions.length === 0 && (
          <Card className="p-2">
            <EmptyState icon={MessagesSquare} title="先到「自動找職缺」或「履歷健檢」提供履歷"
              desc="面試官會依你的真實背景出題；沒有履歷時會用範例背景示意。" />
          </Card>
        )}
      </div>
    )
  }

  // ---- 出題中 ----
  if (cur.loading) {
    return (
      <div>
        {tabs}
        <Card className="p-8">
          <div className="flex flex-col items-center gap-3 text-slate-500">
            <Loader2 className="w-7 h-7 animate-spin text-brand-500" />
            <p className="text-sm">AI 面試官正在依「{cur.title}」這份職缺出題…</p>
            <Button variant="danger" icon={XCircle} onClick={() => stopSessionTask(cur.key)}>停止</Button>
          </div>
        </Card>
      </div>
    )
  }

  // ---- 出題失敗 ----
  if (cur.error && !cur.questions.length) {
    return (
      <div>
        {tabs}
        <Card className="p-6">
          <p className="text-sm text-rose-600 mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{cur.error}</p>
          <Button variant="secondary" icon={RefreshCw} onClick={() => beginQuestions(cur.key, cur.jd, cur.profile)}>重試出題</Button>
        </Card>
      </div>
    )
  }

  // ---- 總評 ----
  if (cur.summary) {
    return (
      <div className="space-y-4 animate-fade-in-up">
        {tabs}
        <Card className="p-6 flex items-center gap-6">
          <ScoreRing score={cur.summary.overall_score} size={110} />
          <div>
            <h2 className="text-lg font-bold mb-1">面試總評 · {cur.title}</h2>
            <p className="text-sm text-slate-600">{cur.summary.summary}</p>
          </div>
        </Card>
        {cur.summary.advice.length > 0 && (
          <Card className="p-5">
            <h3 className="font-bold mb-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-500" />接下來最該補強</h3>
            <ul className="list-disc pl-5 text-sm space-y-1 text-slate-700">
              {cur.summary.advice.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </Card>
        )}
        <Button variant="secondary" icon={RefreshCw} onClick={() => beginQuestions(cur.key, cur.jd, cur.profile)}>再來一場</Button>
      </div>
    )
  }

  // ---- 逐題 ----
  const q = cur.questions[cur.idx]
  return (
    <div className="space-y-4">
      {tabs}
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-500">{cur.title}｜第 {cur.idx + 1} / {cur.questions.length} 題</span>
        <div className="flex items-center gap-2">
          {cur.busy && <Button variant="danger" size="sm" icon={XCircle} onClick={() => stopSessionTask(cur.key)}>停止</Button>}
          <Button variant="ghost" size="sm" icon={RefreshCw} disabled={cur.busy}
            onClick={() => beginQuestions(cur.key, cur.jd, cur.profile)}>
            重新開始
          </Button>
        </div>
      </div>
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-2">
          {q?.category && <Badge tone="brand">{q.category}</Badge>}
          <span className="text-xs text-slate-400">面試官提問</span>
        </div>
        <p className="text-base font-medium text-slate-900">{q?.question}</p>
      </Card>

      {!cur.feedback ? (
        <Card className="p-5">
          <textarea
            className="w-full border border-slate-300 rounded-lg p-3 text-sm h-36 focus:outline-none focus:ring-2 focus:ring-brand-200"
            placeholder="輸入你的回答…" value={cur.answer} onChange={(e) => setAnswer(e.target.value)} />
          <div className="mt-3">
            <Button onClick={submitAnswer} loading={cur.busy} disabled={!cur.answer.trim()} icon={CheckCircle2}>送出回答</Button>
            {cur.busy && <Button variant="danger" icon={XCircle} onClick={() => stopSessionTask(cur.key)} className="ml-2">停止</Button>}
          </div>
        </Card>
      ) : (
        <Card className="p-5 avoid-break animate-fade-in-up">
          <div className="flex items-center gap-4 mb-3">
            <ScoreRing score={cur.feedback.score} size={84} />
            <div className="text-sm text-slate-600">這題的即時回饋</div>
          </div>
          {cur.feedback.strengths.length > 0 && (<>
            <p className="text-sm font-medium mt-2 mb-1 text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-4 h-4" />做得好</p>
            <ul className="list-disc pl-5 text-sm space-y-1 text-slate-700">{cur.feedback.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </>)}
          {cur.feedback.improvements.length > 0 && (<>
            <p className="text-sm font-medium mt-3 mb-1 text-amber-700 flex items-center gap-1"><AlertTriangle className="w-4 h-4" />可改進</p>
            <ul className="list-disc pl-5 text-sm space-y-1 text-slate-700">{cur.feedback.improvements.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </>)}
          {cur.feedback.sample_answer && (<>
            <p className="text-sm font-medium mt-3 mb-1 text-slate-700">示範答法</p>
            <p className="text-sm whitespace-pre-wrap leading-relaxed text-slate-600 bg-slate-50 rounded-lg p-3">{cur.feedback.sample_answer}</p>
          </>)}
          <div className="mt-4">
            <Button onClick={next} loading={cur.busy} icon={ArrowRight}>
              {cur.idx < cur.questions.length - 1 ? "下一題" : "看總評"}
            </Button>
            {cur.busy && <Button variant="danger" icon={XCircle} onClick={() => stopSessionTask(cur.key)} className="ml-2">停止</Button>}
          </div>
        </Card>
      )}
      {cur.error && <p className="text-sm text-rose-600">{cur.error}</p>}
    </div>
  )
}
