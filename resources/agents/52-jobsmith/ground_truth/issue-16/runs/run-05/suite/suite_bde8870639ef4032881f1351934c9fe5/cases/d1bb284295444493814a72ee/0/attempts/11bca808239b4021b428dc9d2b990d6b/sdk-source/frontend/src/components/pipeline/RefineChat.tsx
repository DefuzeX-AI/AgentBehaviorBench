import { useRef, useState } from "react"
import type { UserProfile, RefineUpdate } from "../../types"
import { newTaskId, stopTask } from "../../lib/taskControl"
import { Button } from "../../ui/Button"
import { MessageSquare, Sparkles, ChevronDown, CheckCircle2, XCircle } from "../../ui/icons"

type Msg = { role: "user" | "assistant"; content: string; applied?: boolean }

// 與 AI 多輪討論修改履歷／求職信；AI 回覆建議，若給出修訂則直接套用到可編輯欄位。
export function RefineChat(
  { docType, current, jd, profile, onApply }:
  {
    docType: "resume" | "cover"
    current: string
    jd: string
    profile: UserProfile | null
    onApply: (u: RefineUpdate) => void
  },
) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const taskIdRef = useRef("")
  const label = docType === "resume" ? "履歷" : "求職信"

  async function send() {
    const content = input.trim()
    if (!content || busy) return
    const next: Msg[] = [...messages, { role: "user", content }]
    const ctrl = new AbortController()
    const taskId = newTaskId(`refine-${docType}`)
    abortRef.current = ctrl
    taskIdRef.current = taskId
    setMessages(next); setInput(""); setBusy(true)
    try {
      const r = await fetch("/api/pipeline/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          doc_type: docType, current, jd_text: jd, profile,
          task_id: taskId,
          messages: next.map((m) => ({ role: m.role, content: m.content })),
        }),
      })
      const d = await r.json()
      if (!r.ok) {
        setMessages((m) => [...m, { role: "assistant", content: d.error || "發生錯誤，請稍後再試。" }])
        return
      }
      const applied = Boolean(d.updated)
      if (applied) onApply(d.updated as RefineUpdate)
      setMessages((m) => [...m, { role: "assistant", content: d.reply || "（無回覆）", applied }])
    } catch (e) {
      if ((e as Error)?.name === "AbortError") {
        setMessages((m) => [...m, { role: "assistant", content: "已停止任務。" }])
        return
      }
      setMessages((m) => [...m, { role: "assistant", content: "連線發生問題，請確認伺服器是否啟動。" }])
    } finally {
      if (abortRef.current === ctrl) {
        setBusy(false)
        abortRef.current = null
        taskIdRef.current = ""
      }
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }))
    }
  }

  async function stopSend() {
    try {
      await stopTask(taskIdRef.current)
    } catch {
      // 停止端點失敗時仍中止前端等待。
    } finally {
      abortRef.current?.abort()
      setBusy(false)
    }
  }

  return (
    <div className="no-print mt-2">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="text-sm text-brand-600 hover:text-brand-700 inline-flex items-center gap-1.5 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300">
        <MessageSquare className="w-4 h-4" />跟 AI 討論修改{label}
        <ChevronDown className={`w-4 h-4 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 border border-slate-200 rounded-lg p-3 bg-slate-50/60">
          {messages.length > 0 && (
            <div ref={scrollRef} className="space-y-2 mb-2 max-h-72 overflow-y-auto">
              {messages.map((m, i) => (
                <div key={i} className={m.role === "user" ? "text-right" : ""}>
                  <span className={`inline-block text-sm rounded-lg px-3 py-1.5 whitespace-pre-wrap text-left ${
                    m.role === "user" ? "bg-brand-600 text-white" : "bg-white border border-slate-200 text-slate-700"
                  }`}>
                    {m.content}
                  </span>
                  {m.applied && (
                    <p className="text-xs text-emerald-600 mt-0.5 inline-flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />已套用到上方{label}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <input value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send() }}
              disabled={busy} aria-label={`與 AI 討論${label}`}
              placeholder="例如：更強調我的 LLM 經驗、語氣再專業些…"
              className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:opacity-50" />
            <Button onClick={send} loading={busy} icon={Sparkles} size="sm">送出</Button>
            {busy && <Button onClick={stopSend} variant="danger" icon={XCircle} size="sm">停止</Button>}
          </div>
          <p className="text-xs text-slate-400 mt-1.5">AI 會回覆建議；若有修訂會直接套用到上方{label}欄位，可再手動微調。</p>
        </div>
      )}
    </div>
  )
}
