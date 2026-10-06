import { cn } from "@/lib/utils";
import type { SessionStatus } from "@/stores/sessionStore";
import type { WorkflowMode } from "@/types/ui";

interface WorkflowStatusPanelProps {
  status: SessionStatus;
  currentStep: string | null;
  mode: WorkflowMode;
}

interface WorkflowStep {
  id: string;
  label: string;
}

const DRAFT_STEPS: WorkflowStep[] = [
  { id: "extract_tech_node", label: "技术要点提取" },
  { id: "drawing_analyze_node", label: "附图分析" },
  { id: "draft_claims_node", label: "权利要求生成" },
  { id: "traceability_check_node", label: "可追溯性检查" },
  { id: "human_review_node", label: "权利要求确认" },
  { id: "write_spec_node", label: "说明书撰写" },
  { id: "logic_review_node", label: "逻辑审查" },
];

const OA_STEPS: WorkflowStep[] = [
  { id: "application_baseline_agent", label: "本案分析" },
  { id: "oa_parser_node", label: "审查意见分析" },
  { id: "multimodal_prior_art_agent", label: "对比文件核验" },
  { id: "concession_and_gap_node", label: "修改方向确认" },
  { id: "fallback_feature_miner_node", label: "说明书特征挖掘" },
  { id: "prior_art_stress_tester_node", label: "候选特征审查" },
  { id: "strategy_decision_node", label: "答复策略" },
  { id: "claim_amendment_agent", label: "权利要求修改" },
  { id: "argument_writer_agent", label: "答辩正文" },
  { id: "spec_update_agent", label: "说明书修改" },
  { id: "response_traceability_node", label: "逻辑审查" },
];

const COMPARE_STEPS: WorkflowStep[] = [
  { id: "multimodal_draft_parser_node", label: "申请文件分析" },
  { id: "multimodal_prior_art_node", label: "对比文件分析" },
  { id: "multimodal_matrix_comparison_node", label: "特征比对" },
  { id: "risk_assessment_node", label: "风险评估" },
  { id: "amendment_suggestion_node", label: "修改建议" },
];

const POLISH_STEPS: WorkflowStep[] = [
  { id: "multimodal_diagnostic_analyzer_node", label: "申请文件分析" },
  { id: "multimodal_synergy_miner_node", label: "特征挖掘" },
  { id: "claim_architect_node", label: "权利要求润色" },
  { id: "specification_amplifier_node", label: "说明书润色" },
  { id: "multimodal_adversarial_reviewer_node", label: "逻辑审查" },
];

export function WorkflowStatusPanel({ status, currentStep, mode }: WorkflowStatusPanelProps) {
  const steps =
    mode === "oa"
      ? OA_STEPS
      : mode === "compare"
        ? COMPARE_STEPS
        : mode === "polish"
          ? POLISH_STEPS
          : DRAFT_STEPS;
  const activeIdx = steps.findIndex((item) => item.id === currentStep);

  return (
    <section className="rounded-2xl border border-sky-100 bg-white/90 p-4 shadow-sm backdrop-blur">
      <h2 className="text-base font-semibold text-slate-900">流程状态</h2>
      <p className="mt-1 text-xs text-slate-500">当前状态：{status ?? "idle"}</p>
      <ul className="mt-4 space-y-2">
        {steps.map((step, idx) => {
          const isActive = currentStep === step.id;
          const isDone = status === "completed" || (activeIdx >= 0 && idx < activeIdx);
          return (
            <li
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3 py-2 text-sm",
                isActive
                  ? "border-sky-500 bg-sky-50 text-sky-900"
                  : isDone
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-slate-200 bg-white text-slate-600",
              )}
              key={step.id}
            >
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border text-[11px] font-semibold">
                {isActive ? ">" : isDone ? "v" : "-"}
              </span>
              <span>{step.label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
