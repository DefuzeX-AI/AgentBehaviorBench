import { useEffect, useState } from "react";
import type { LlmProvider, LlmSettings } from "@/stores/llmSettingsStore";

type SaveStatus = "IDLE" | "SAVING" | "SAVED";

interface SettingsViewProps {
  settings: LlmSettings;
  onSave: (next: LlmSettings) => void;
  onReset: () => void;
}

type ProviderConfig = {
  value: LlmProvider;
  label: string;
  defaultBaseUrl: string;
};

type MinimalInputProps = {
  label: string;
  type?: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
};

type MinimalSelectProps = {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  hint?: string;
};

function MinimalInput({
  label,
  type = "text",
  placeholder,
  value,
  onChange,
  hint,
}: MinimalInputProps) {
  return (
    <div className="space-y-2">
      <strong className="block text-[14.5px] text-gray-900">{label}</strong>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-sm border border-gray-300 bg-transparent px-3.5 py-2 font-mono text-[14.5px] text-gray-900 placeholder:font-sans placeholder:text-gray-400 transition-colors focus:border-gray-900 focus:outline-none focus:ring-0"
      />
      {hint ? (
        <div className="mt-2 border-l-2 border-gray-200 pl-3">
          <p className="font-serif text-[13px] italic leading-relaxed text-gray-500">{hint}</p>
        </div>
      ) : null}
    </div>
  );
}

function MinimalSelect({
  label,
  value,
  options,
  onChange,
  hint,
}: MinimalSelectProps) {
  return (
    <div className="space-y-2">
      <strong className="block text-[14.5px] text-gray-900">{label}</strong>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full cursor-pointer appearance-none rounded-sm border border-gray-300 bg-transparent px-3.5 py-2 text-[14.5px] text-gray-900 transition-colors focus:border-gray-900 focus:outline-none focus:ring-0"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%234B5563'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E\")",
          backgroundPosition: "right 0.75rem center",
          backgroundRepeat: "no-repeat",
          backgroundSize: "1.2em 1.2em",
        }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint ? (
        <div className="mt-2 border-l-2 border-gray-200 pl-3">
          <p className="font-serif text-[13px] italic leading-relaxed text-gray-500">{hint}</p>
        </div>
      ) : null}
    </div>
  );
}

const PROVIDERS: ProviderConfig[] = [
  { value: "qwen", label: "千问 (Qwen)", defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "doubao", label: "豆包 (Doubao)", defaultBaseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
  { value: "deepseek", label: "DeepSeek", defaultBaseUrl: "https://api.deepseek.com/v1" },
  { value: "glm", label: "GLM", defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4" },
  { value: "minimax", label: "MiniMax", defaultBaseUrl: "https://api.minimax.chat/v1" },
  { value: "kimi", label: "Kimi", defaultBaseUrl: "https://api.moonshot.cn/v1" },
  { value: "openai", label: "OpenAI", defaultBaseUrl: "https://api.openai.com/v1" },
  { value: "claude", label: "Claude", defaultBaseUrl: "https://api.anthropic.com" },
  { value: "gemini", label: "Gemini", defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta" },
];

function toNumber(value: string, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function getProviderDefaultBaseUrl(provider: LlmProvider): string {
  return PROVIDERS.find((item) => item.value === provider)?.defaultBaseUrl ?? "";
}

export default function SettingsView({ settings, onSave, onReset }: SettingsViewProps) {
  const [draft, setDraft] = useState<LlmSettings>(settings);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("IDLE");

  useEffect(() => {
    setDraft((prev) => {
      const next = { ...settings };
      if (!next.baseUrl.trim()) {
        next.baseUrl = getProviderDefaultBaseUrl(next.provider);
      }
      return next;
    });
  }, [settings]);

  const handleProviderChange = (nextProvider: LlmProvider) => {
    setDraft((prev) => {
      const prevDefault = getProviderDefaultBaseUrl(prev.provider);
      const nextDefault = getProviderDefaultBaseUrl(nextProvider);
      const shouldReplaceBaseUrl = !prev.baseUrl.trim() || prev.baseUrl.trim() === prevDefault;
      return {
        ...prev,
        provider: nextProvider,
        baseUrl: shouldReplaceBaseUrl ? nextDefault : prev.baseUrl,
      };
    });
  };

  const handleSave = () => {
    setSaveStatus("SAVING");
    onSave({
      ...draft,
      temperature: Math.max(0, Math.min(2, draft.temperature)),
      maxReflections: Math.max(1, Math.min(10, Math.round(draft.maxReflections))),
    });
    window.setTimeout(() => setSaveStatus("SAVED"), 300);
    window.setTimeout(() => setSaveStatus("IDLE"), 1800);
  };

  return (
    <div className="mx-auto w-full max-w-4xl animate-fade-in-up pb-32 pt-10 font-sans text-gray-800">
      <div className="mb-16 flex items-end justify-between border-b border-gray-200 pb-10">
        <div>
          <h2 className="mb-3 text-3xl font-bold tracking-tight text-gray-900">全局设置</h2>
        </div>
      </div>

      <div className="space-y-24">
        <section>
          <h3 className="mb-10 border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
            LLM配置
          </h3>
          <div className="grid grid-cols-1 gap-x-12 gap-y-10 pl-2 md:grid-cols-2">
            <MinimalSelect
              label="模型厂商"
              value={draft.provider}
              onChange={(value) => handleProviderChange(value as LlmProvider)}
              options={PROVIDERS.map((item) => ({ value: item.value, label: item.label }))}
            />
            <MinimalInput
              label="文本推理模型"
              value={draft.model}
              onChange={(value) => setDraft((s) => ({ ...s, model: value }))}
            />
            <MinimalInput
              label="视觉解析模型"
              value={draft.visionModel}
              onChange={(value) => setDraft((s) => ({ ...s, visionModel: value }))}
            />
            <MinimalInput
              label="温度系数 (Temperature)"
              type="number"
              value={String(draft.temperature)}
              onChange={(value) => setDraft((s) => ({ ...s, temperature: toNumber(value, s.temperature) }))}
            />
            <div className="md:col-span-2">
              <MinimalInput
                label="API Key"
                type="password"
                placeholder="sk-..."
                value={draft.apiKey}
                onChange={(value) => setDraft((s) => ({ ...s, apiKey: value }))}
              />
            </div>
            <div className="md:col-span-2">
              <MinimalInput
                label="Base URL"
                value={draft.baseUrl}
                onChange={(value) => setDraft((s) => ({ ...s, baseUrl: value }))}
                placeholder={getProviderDefaultBaseUrl(draft.provider)}
              />
            </div>
          </div>
        </section>

        <section>
          <h3 className="mb-10 border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
            撰写参数
          </h3>
          <div className="grid grid-cols-1 gap-x-12 gap-y-10 pl-2 md:grid-cols-2">
            <MinimalSelect
              label="逻辑审查上限"
              value={String(draft.maxReflections)}
              onChange={(value) => setDraft((s) => ({ ...s, maxReflections: Math.max(1, toNumber(value, s.maxReflections)) }))}
              options={[
                { value: "1", label: "1 轮 (速度优先)" },
                { value: "3", label: "3 轮 (推荐)" },
                { value: "5", label: "5 轮 (更严谨)" },
              ]}
            />
            <MinimalSelect
              label="上下文截断策略"
              value={draft.contextWindowLimit}
              onChange={(value) => setDraft((s) => ({ ...s, contextWindowLimit: value }))}
              options={[
                { value: "32k", label: "32K Tokens" },
                { value: "128k", label: "128K Tokens (推荐)" },
                { value: "200k", label: "200K+ (需模型支持)" },
              ]}
            />
          </div>
        </section>
      </div>

      <div className="mt-24 flex justify-end gap-4 border-t border-gray-200 pt-8">
        <button
          type="button"
          className="rounded-sm border border-transparent px-6 py-2 text-[14px] font-bold text-gray-500 transition-all hover:border-gray-300"
          onClick={() => {
            onReset();
            setSaveStatus("IDLE");
          }}
        >
          恢复默认
        </button>
        <button
          type="button"
          onClick={handleSave}
          className="rounded-sm border border-gray-900 bg-gray-900 px-8 py-2 text-[14px] font-bold text-white shadow-sm transition-all hover:bg-black"
        >
          {saveStatus === "SAVING" ? "保存中..." : "保存配置"}
        </button>
      </div>
    </div>
  );
}
