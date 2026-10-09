import { WORKFLOW_OUTPUTS, WORKFLOW_STEPS, getWorkflowOutputValue, type GlobalTab } from "@/components/workflow/workflowConfig";
import type { SessionStatus } from "@/stores/sessionStore";
import type { TimelineNodeVM } from "@/types/ui";

type WorkflowTab = Exclude<GlobalTab, "home" | "settings">;

function isWorkflowTab(mode: GlobalTab): mode is WorkflowTab {
  return mode !== "home" && mode !== "settings";
}

function normalizeStepForTimeline(mode: WorkflowTab, currentStep: string | null): string | null {
  if (mode !== "draft" || !currentStep) return currentStep;
  if (currentStep === "claims_revise_review_node" || currentStep === "revise_claims_node") {
    return "human_review_node";
  }
  if (currentStep === "spec_review_node") {
    return "logic_review_node";
  }
  if (currentStep === "targeted_revise_spec_node") {
    return "logic_review_node";
  }
  return currentStep;
}

function hasNodeData(mode: WorkflowTab, nodeId: string, data: Record<string, unknown> | null): boolean {
  if (!data) return false;
  const def = WORKFLOW_OUTPUTS[mode].find((item) => item.nodeId === nodeId);
  if (!def) return false;
  const value = getWorkflowOutputValue(mode, def.valueKey, data);
  return value !== null && value !== undefined;
}

export function buildTimelineNodes(params: {
  mode: GlobalTab;
  status: SessionStatus;
  currentStep: string | null;
  data: Record<string, unknown> | null;
  hasSession: boolean;
}): TimelineNodeVM[] {
  const { mode, status, currentStep, data, hasSession } = params;
  if (!isWorkflowTab(mode)) return [];
  const normalizedStep = normalizeStepForTimeline(mode, currentStep);

  const steps = WORKFLOW_STEPS[mode];
  const activeIdx = steps.findIndex((s) => s.id === normalizedStep);
  // IMPORTANT: timeline highlighting must be scoped to the active workflow session only.
  // Do not infer started from global status, otherwise other tabs appear incorrectly "lit".
  const started = hasSession;

  const nodes: TimelineNodeVM[] = [
    {
      id: "upload",
      label: "上传文件",
      state: started ? "done" : "ready",
      clickable: true,
      hasData: started,
    },
  ];

  for (let idx = 0; idx < steps.length; idx += 1) {
    const step = steps[idx];
    const hasDataForStep = hasNodeData(mode, step.id, data);

    let state: TimelineNodeVM["state"] = "locked";
    if (!started) {
      state = "locked";
    } else if (status === "completed") {
      state = "done";
    } else if (activeIdx === -1) {
      state = idx === 0 ? "running" : hasDataForStep ? "done" : "locked";
    } else if (idx < activeIdx) {
      state = "done";
    } else if (idx === activeIdx) {
      if (status === "waiting_human") state = "waiting_human";
      else if (status === "failed" || status === "cancelled") state = "error";
      else state = "running";
    } else {
      state = "locked";
    }

    nodes.push({
      id: step.id,
      label: step.label,
      state,
      clickable: state === "done" || state === "waiting_human",
      hasData: hasDataForStep,
    });
  }

  return nodes;
}

export function getAutoSelectedNodeId(params: {
  mode: GlobalTab;
  status: SessionStatus;
  currentStep: string | null;
  hasSession: boolean;
}): string {
  const { mode, status, currentStep, hasSession } = params;
  if (!isWorkflowTab(mode)) return "upload";
  const normalizedStep = normalizeStepForTimeline(mode, currentStep);
  if (!hasSession) return "upload";
  if ((status === "running" || status === "waiting_human" || status === "queued") && normalizedStep) {
    return normalizedStep;
  }
  if ((status === "failed" || status === "cancelled") && normalizedStep) {
    return normalizedStep;
  }
  return "upload";
}
