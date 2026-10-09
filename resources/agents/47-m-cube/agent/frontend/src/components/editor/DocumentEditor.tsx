import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type EditorTab = "claims" | "traceability" | "specification" | "oa_reply";

interface DocumentEditorProps {
  claims: Record<string, unknown> | null;
  claimTraceability: Record<string, unknown> | null;
  specification: Record<string, unknown> | null;
  oaReply: string;
  onClaimsChange: (text: string) => void;
  onClaimTraceabilityChange: (text: string) => void;
  onSpecificationChange: (text: string) => void;
  onOaReplyChange: (text: string) => void;
}

const TABS: Array<{ id: EditorTab; label: string }> = [
  { id: "claims", label: "权利要求" },
  { id: "traceability", label: "可追溯性" },
  { id: "specification", label: "说明书" },
  { id: "oa_reply", label: "OA 答复" },
];

function readText(record: Record<string, unknown> | null): string {
  if (!record) {
    return "";
  }
  const value = record.text;
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(record, null, 2);
}

export function DocumentEditor({
  claims,
  claimTraceability,
  specification,
  oaReply,
  onClaimsChange,
  onClaimTraceabilityChange,
  onSpecificationChange,
  onOaReplyChange,
}: DocumentEditorProps) {
  const [tab, setTab] = useState<EditorTab>("claims");

  const content = useMemo(() => {
    if (tab === "claims") return readText(claims);
    if (tab === "specification") return readText(specification);
    if (tab === "traceability") return readText(claimTraceability);
    return oaReply;
  }, [claims, claimTraceability, specification, oaReply, tab]);

  const onChange = (nextValue: string) => {
    if (tab === "claims") return onClaimsChange(nextValue);
    if (tab === "specification") return onSpecificationChange(nextValue);
    if (tab === "traceability") return onClaimTraceabilityChange(nextValue);
    return onOaReplyChange(nextValue);
  };

  return (
    <section className="rounded-2xl border border-sky-100 bg-white/90 p-4 shadow-sm backdrop-blur">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">文档编辑区</h2>
        <span className="text-xs text-slate-500">可直接编辑草稿内容</span>
      </div>
      <div className="mt-3 flex gap-2">
        {TABS.map((item) => (
          <Button
            className={cn(tab === item.id ? "" : "opacity-80")}
            key={item.id}
            onClick={() => setTab(item.id)}
            size="sm"
            variant={tab === item.id ? "default" : "outline"}
          >
            {item.label}
          </Button>
        ))}
      </div>
      <textarea
        className="mt-3 h-72 w-full resize-y rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
        onChange={(event) => onChange(event.target.value)}
        placeholder="在此查看或编辑文档内容..."
        value={content}
      />
    </section>
  );
}
