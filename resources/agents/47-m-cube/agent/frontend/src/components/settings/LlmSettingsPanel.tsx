import { Button } from "@/components/ui/button";
import type { LlmProvider } from "@/stores/llmSettingsStore";

interface LlmSettingsPanelProps {
  provider: LlmProvider;
  model: string;
  visionModel: string;
  apiKey: string;
  baseUrl: string;
  onProviderChange: (provider: LlmProvider) => void;
  onModelChange: (model: string) => void;
  onVisionModelChange: (model: string) => void;
  onApiKeyChange: (apiKey: string) => void;
  onBaseUrlChange: (baseUrl: string) => void;
  onReset: () => void;
}

const PROVIDERS: Array<{ value: LlmProvider; label: string; placeholderModel: string; placeholderBaseUrl: string }> = [
  { value: "openai", label: "OpenAI", placeholderModel: "gpt-4o-mini", placeholderBaseUrl: "https://api.openai.com/v1" },
  { value: "claude", label: "Claude", placeholderModel: "claude-3-7-sonnet-latest", placeholderBaseUrl: "https://api.anthropic.com" },
  { value: "gemini", label: "Gemini", placeholderModel: "gemini-2.0-flash", placeholderBaseUrl: "https://generativelanguage.googleapis.com/v1beta" },
  { value: "kimi", label: "Kimi", placeholderModel: "moonshot-v1-8k", placeholderBaseUrl: "https://api.moonshot.cn/v1" },
  { value: "minimax", label: "MiniMax", placeholderModel: "abab6.5s-chat", placeholderBaseUrl: "https://api.minimax.chat/v1" },
  { value: "qwen", label: "千问 (Qwen)", placeholderModel: "qwen-plus", placeholderBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "doubao", label: "豆包 (Doubao)", placeholderModel: "doubao-1.5-pro-32k", placeholderBaseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
];

export function LlmSettingsPanel({
  provider,
  model,
  visionModel,
  apiKey,
  baseUrl,
  onProviderChange,
  onModelChange,
  onVisionModelChange,
  onApiKeyChange,
  onBaseUrlChange,
  onReset,
}: LlmSettingsPanelProps) {
  const selected = PROVIDERS.find((item) => item.value === provider) ?? PROVIDERS[0];

  return (
    <section className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">LLM 设置</h2>
      <p className="mt-1 text-xs text-slate-500">
        这里填写你自己的模型配置。API Key 只保存在前端内存，不写入 localStorage。
      </p>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">模型厂商</span>
          <select
            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm"
            onChange={(event) => onProviderChange(event.target.value as LlmProvider)}
            value={provider}
          >
            {PROVIDERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">模型名</span>
          <input
            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm"
            onChange={(event) => onModelChange(event.target.value)}
            placeholder={selected.placeholderModel}
            type="text"
            value={model}
          />
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">视觉模型名</span>
          <input
            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm"
            onChange={(event) => onVisionModelChange(event.target.value)}
            placeholder={selected.placeholderModel}
            type="text"
            value={visionModel}
          />
        </label>

        <label className="text-sm md:col-span-2">
          <span className="mb-1 block font-medium text-slate-700">API Key</span>
          <input
            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm"
            onChange={(event) => onApiKeyChange(event.target.value)}
            placeholder="sk-..."
            type="password"
            value={apiKey}
          />
        </label>

        <label className="text-sm md:col-span-2">
          <span className="mb-1 block font-medium text-slate-700">Base URL (可选)</span>
          <input
            className="w-full rounded-lg border border-slate-200 bg-white p-2 text-sm"
            onChange={(event) => onBaseUrlChange(event.target.value)}
            placeholder={selected.placeholderBaseUrl}
            type="text"
            value={baseUrl}
          />
        </label>
      </div>

      <div className="mt-4 flex justify-end">
        <Button onClick={onReset} size="sm" variant="outline">
          重置默认
        </Button>
      </div>
    </section>
  );
}
