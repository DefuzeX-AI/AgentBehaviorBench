import type { LogEvent } from "@/stores/logStore";

interface StreamingLogPanelProps {
  events: LogEvent[];
}

export function StreamingLogPanel({ events }: StreamingLogPanelProps) {
  return (
    <section className="rounded-2xl border border-sky-100 bg-white/90 p-4 shadow-sm backdrop-blur">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">流式日志</h2>
        <span className="text-xs text-slate-500">{events.length} 条事件</span>
      </div>
      <div className="mt-3 h-64 overflow-auto rounded-lg border border-slate-200 bg-slate-950 p-3 font-mono text-xs text-slate-100">
        {events.length === 0 ? (
          <p className="text-slate-400">暂无事件。</p>
        ) : (
          <ul className="space-y-2">
            {events.map((event, idx) => (
              <li className="rounded bg-slate-900/90 p-2" key={`${event.timestamp}-${idx}`}>
                <div className="text-cyan-300">{event.timestamp}</div>
                <div className="text-amber-300">{event.type}</div>
                <pre className="mt-1 whitespace-pre-wrap break-words text-slate-200">
                  {JSON.stringify(event.payload)}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
