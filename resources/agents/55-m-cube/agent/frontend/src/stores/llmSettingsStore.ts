import { create } from "zustand";

export type LlmProvider =
  | "openai"
  | "claude"
  | "anthropic"
  | "gemini"
  | "kimi"
  | "minimax"
  | "qwen"
  | "doubao"
  | "deepseek"
  | "glm";

export interface LlmSettings {
  provider: LlmProvider;
  model: string;
  visionModel: string;
  apiKey: string;
  baseUrl: string;
  temperature: number;
  maxReflections: number;
  contextWindowLimit: string;
  jurisdictionBaseline: string;
  claimFormatting: string;
}

interface LlmSettingsState extends LlmSettings {
  setSettings: (patch: Partial<LlmSettings>) => void;
  resetSettings: () => void;
}

const LLM_SETTINGS_STORAGE_KEY = "mpa.llmSettings";

const initialState: LlmSettings = {
  provider: "openai",
  model: "gpt-4o-mini",
  visionModel: "gpt-4o-mini",
  apiKey: "",
  baseUrl: "",
  temperature: 0.2,
  maxReflections: 3,
  contextWindowLimit: "128k",
  jurisdictionBaseline: "cnipa",
  claimFormatting: "classic",
};

function loadPersistedSettings(): Partial<LlmSettings> {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(LLM_SETTINGS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Partial<LlmSettings>;
    return {
      provider: parsed.provider,
      model: typeof parsed.model === "string" ? parsed.model : undefined,
      visionModel: typeof parsed.visionModel === "string" ? parsed.visionModel : undefined,
      baseUrl: typeof parsed.baseUrl === "string" ? parsed.baseUrl : undefined,
      apiKey: typeof parsed.apiKey === "string" ? parsed.apiKey : undefined,
      temperature:
        typeof parsed.temperature === "number" && Number.isFinite(parsed.temperature)
          ? parsed.temperature
          : undefined,
      maxReflections:
        typeof parsed.maxReflections === "number" && Number.isFinite(parsed.maxReflections)
          ? parsed.maxReflections
          : undefined,
      contextWindowLimit: typeof parsed.contextWindowLimit === "string" ? parsed.contextWindowLimit : undefined,
      jurisdictionBaseline: typeof parsed.jurisdictionBaseline === "string" ? parsed.jurisdictionBaseline : undefined,
      claimFormatting: typeof parsed.claimFormatting === "string" ? parsed.claimFormatting : undefined,
    };
  } catch {
    return {};
  }
}

function persistSettings(state: LlmSettings): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(
      LLM_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        provider: state.provider,
        model: state.model,
        visionModel: state.visionModel,
        baseUrl: state.baseUrl,
        apiKey: state.apiKey,
        temperature: state.temperature,
        maxReflections: state.maxReflections,
        contextWindowLimit: state.contextWindowLimit,
        jurisdictionBaseline: state.jurisdictionBaseline,
        claimFormatting: state.claimFormatting,
      }),
    );
  } catch {
    // Ignore storage errors to avoid breaking UI interactions.
  }
}

const bootState: LlmSettings = {
  ...initialState,
  ...loadPersistedSettings(),
};

export const useLlmSettingsStore = create<LlmSettingsState>((set) => ({
  ...bootState,
  setSettings: (patch) =>
    set((state) => {
      const next = { ...state, ...patch };
      persistSettings(next);
      return next;
    }),
  resetSettings: () =>
    set(() => {
      persistSettings(initialState);
      return initialState;
    }),
}));
