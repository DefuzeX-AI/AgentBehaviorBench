import { useEffect, useMemo, useState } from "react";
import type { GlobalTab } from "@/components/workflow/workflowConfig";
import { WORKFLOW_OUTPUTS } from "@/components/workflow/workflowConfig";

interface NodeOutputAccordionProps {
  mode: GlobalTab;
  currentStep: string | null;
  data: Record<string, unknown> | null;
}

function toText(value: unknown): string {
  if (value === null || value === undefined) return "暂无输出";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function NodeOutputAccordion({ mode, currentStep, data }: NodeOutputAccordionProps) {
  const outputs = useMemo(() => {
    if (mode === "home" || mode === "settings") return [];
    return WORKFLOW_OUTPUTS[mode];
  }, [mode]);

  const defaultOpen = useMemo(() => {
    if (outputs.length === 0) return "";
    if (currentStep && outputs.some((o) => o.nodeId === currentStep)) return currentStep;
    if (data) {
      const first = outputs.find((o) => data[o.valueKey] !== undefined && data[o.valueKey] !== null);
      if (first) return first.nodeId;
    }
    return outputs[0]?.nodeId ?? "";
  }, [outputs, currentStep, data]);

  const [openNode, setOpenNode] = useState(defaultOpen);

  useEffect(() => {
    setOpenNode(defaultOpen);
  }, [defaultOpen]);

  if (mode === "home" || mode === "settings") return null;

  return (
    <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-gray-100">
      <h3 className="text-sm font-semibold text-gray-800">节点输出</h3>
      <p className="mt-1 text-xs text-gray-500">按流程顺序展示，可选择查看单个节点输出</p>
      <div className="mt-3 space-y-2">
        {outputs.map((item) => {
          const isOpen = openNode === item.nodeId;
          const value = data?.[item.valueKey];
          return (
            <div className="rounded-lg border border-gray-200" key={item.nodeId}>
              <button className="flex w-full items-center justify-between px-3 py-2 text-left" onClick={() => setOpenNode(isOpen ? "" : item.nodeId)} type="button">
                <span className="text-sm text-gray-800">{item.title}</span>
                <span className="text-xs text-gray-500">{isOpen ? "收起" : "展开"}</span>
              </button>
              {isOpen ? (
                <pre className="max-h-72 overflow-auto border-t border-gray-100 bg-gray-50 p-3 text-xs text-gray-700">{toText(value)}</pre>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

