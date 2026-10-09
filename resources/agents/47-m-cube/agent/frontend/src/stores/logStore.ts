import { create } from "zustand";

export interface LogEvent {
  timestamp: string;
  type: string;
  payload: Record<string, unknown>;
}

interface LogState {
  events: LogEvent[];
  appendEvent: (event: LogEvent) => void;
  clearEvents: () => void;
}

export const useLogStore = create<LogState>((set) => ({
  events: [],
  appendEvent: (event) => set((state) => ({ events: [...state.events, event] })),
  clearEvents: () => set({ events: [] }),
}));
