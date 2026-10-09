import { Button } from "@/components/ui/button";

interface SessionControlBarProps {
  hasSession: boolean;
  busy?: boolean;
  onRefreshStatus: () => void;
  onCancel: () => void;
  onReconnect: () => void;
}

export function SessionControlBar({
  hasSession,
  busy = false,
  onRefreshStatus,
  onCancel,
  onReconnect,
}: SessionControlBarProps) {
  return (
    <section className="rounded-2xl border border-sky-100 bg-white/90 p-4 shadow-sm backdrop-blur">
      <h2 className="text-base font-semibold text-slate-900">会话控制</h2>
      <div className="mt-2 text-xs text-slate-500">在当前工作页签中管理会话连接、刷新和取消操作。</div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Button disabled={!hasSession || busy} onClick={onRefreshStatus} size="sm" variant="outline">
          刷新状态
        </Button>
        <Button disabled={!hasSession || busy} onClick={onReconnect} size="sm" variant="outline">
          重连 SSE
        </Button>
        <Button className="col-span-2" disabled={!hasSession || busy} onClick={onCancel} variant="outline">
          取消会话
        </Button>
      </div>
    </section>
  );
}
