import { create } from "zustand";

export type SessionStatus =
  | "queued"
  | "running"
  | "waiting_human"
  | "completed"
  | "failed"
  | "cancelled"
  | null;

interface SessionState {
  sessionId: string | null;
  requestId: string | null;
  status: SessionStatus;
  currentStep: string | null;
  llmMode: string | null;
  llmRuntime: Record<string, unknown> | null;
  visionMode: string | null;
  sessionData: Record<string, unknown> | null;
  setSession: (meta: Partial<Omit<SessionState, "setSession" | "resetSession">>) => void;
  resetSession: () => void;
}

const initialState = {
  sessionId: null,
  requestId: null,
  status: null,
  currentStep: null,
  llmMode: null,
  llmRuntime: null,
  visionMode: null,
  sessionData: null,
};

export const useSessionStore = create<SessionState>((set) => ({
  ...initialState,
  // Merge updates from API/SSE incrementally without losing untouched fields.
  setSession: (meta) => set((state) => ({ ...state, ...meta })),
  resetSession: () => set(initialState),
}));
