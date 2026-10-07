import type { SessionStatus } from "@/types/api";

export type WorkflowMode = "draft" | "oa" | "compare" | "polish" | null;

export interface SessionViewModel {
  sessionId: string | null;
  requestId: string | null;
  status: SessionStatus | null;
  currentStep: string | null;
  mode: WorkflowMode;
}

export type TimelineNodeState =
  | "locked"
  | "ready"
  | "running"
  | "done"
  | "waiting_human"
  | "error";

export interface TimelineNodeVM {
  id: string;
  label: string;
  state: TimelineNodeState;
  clickable: boolean;
  hasData: boolean;
}
