import { cn } from "@/lib/utils";
import type { SessionStatus } from "@/stores/sessionStore";
import type { GlobalTab, WorkflowStepConfig } from "@/components/workflow/workflowConfig";
import { WORKFLOW_STEPS } from "@/components/workflow/workflowConfig";

interface AgentTimelineProps {
  mode: GlobalTab;
  status: SessionStatus;
  currentStep: string | null;
}

function statusOfStep(stepId: string, currentStep: string | null, steps: WorkflowStepConfig[], status: SessionStatus) {
  if (status === "failed" && currentStep === stepId) return "failed" as const;
  if (status === "waiting_human" && currentStep === stepId) return "waiting" as const;
  if (currentStep === stepId) return "running" as const;

  const activeIdx = steps.findIndex((s) => s.id === currentStep);
  const idx = steps.findIndex((s) => s.id === stepId);
  if (status === "completed" || (activeIdx >= 0 && idx >= 0 && idx < activeIdx)) return "done" as const;
  return "pending" as const;
}

export function AgentTimeline({ mode, status, currentStep }: AgentTimelineProps) {
  if (mode === "home" || mode === "settings") return null;

  const steps = WORKFLOW_STEPS[mode];
  return (
    <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-gray-100">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">智能体流程</h3>
        <span className="text-xs text-gray-500">状态：{status ?? "idle"}</span>
      </div>
      <ol className="space-y-3">
        {steps.map((step, idx) => {
          const stepStatus = statusOfStep(step.id, currentStep, steps, status);
          return (
            <li className="relative pl-8" key={step.id}>
              {idx < steps.length - 1 ? <span className="absolute left-[11px] top-5 h-8 w-px bg-gray-200" /> : null}
              <span
                className={cn(
                  "absolute left-0 top-0 inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs",
                  stepStatus === "done" && "border-emerald-500 text-emerald-500",
                  stepStatus === "running" && "border-gray-700 text-gray-700",
                  stepStatus === "waiting" && "border-amber-500 text-amber-500",
                  stepStatus === "failed" && "border-amber-500 text-amber-500",
                  stepStatus === "pending" && "border-gray-300 text-gray-400",
                )}
              >
                {stepStatus === "done" ? "?" : stepStatus === "running" ? "…" : stepStatus === "waiting" ? "!" : stepStatus === "failed" ? "x" : "·"}
              </span>
              <div>
                <p className="text-sm text-gray-800">{step.label}</p>
                <p className="text-xs text-gray-500">{step.id}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

