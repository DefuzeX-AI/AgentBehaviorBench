import type { ApiEnvelope, SessionEventPayload } from "@/types/api";

export interface SessionEnvelopeView {
  requestId: string;
  sessionId: string;
  status: "queued" | "running" | "waiting_human" | "completed" | "failed" | "cancelled";
  currentStep: string | null;
  llmMode: string | null;
  llmRuntime: Record<string, unknown> | null;
  visionMode: string | null;
  sessionData: Record<string, unknown> | null;
}

export interface DocumentEnvelopeView {
  disclosureText: string;
  disclosureImagesMeta: Array<Record<string, unknown>>;
  claims: Record<string, unknown> | null;
  drawingMap: Record<string, unknown> | null;
  claimTraceability: Record<string, unknown> | null;
  specification: Record<string, unknown> | null;
  visualReport: Record<string, unknown> | null;
  applicationImagesMeta: Array<Record<string, unknown>>;
  priorArtImagesMeta: Array<Record<string, unknown>>;
  visionWarnings: Array<Record<string, unknown>>;
  oaReply: string;
  oaSourceText: string;
  oaNoticeFocusText: string;
  oaNoticeFocusApplied: boolean;
}

export function mapSessionEnvelope(envelope: ApiEnvelope): SessionEnvelopeView {
  const data = (envelope.data ?? null) as Record<string, unknown> | null;
  return {
    requestId: envelope.request_id,
    sessionId: envelope.session_id,
    status: envelope.status,
    currentStep: readCurrentStep(data),
    llmMode: readStringField(data, "llm_mode"),
    llmRuntime: readObject(data?.llm_runtime),
    visionMode: readStringField(data, "vision_mode"),
    sessionData: data,
  };
}

export function mapDocumentEnvelope(envelope: ApiEnvelope): DocumentEnvelopeView {
  const data = (envelope.data ?? {}) as Record<string, unknown>;
  return {
    disclosureText: typeof data.disclosure_text === "string" ? data.disclosure_text : "",
    disclosureImagesMeta: readObjectArray(data.disclosure_images_meta),
    claims: readObject(data.claims),
    drawingMap: readObject(data.drawing_map),
    claimTraceability: readObject(data.claim_traceability),
    specification: readObject(data.specification),
    visualReport: readObject(data.visual_report),
    applicationImagesMeta: readObjectArray(data.application_images_meta),
    priorArtImagesMeta: readObjectArray(data.prior_art_images_meta),
    visionWarnings: readObjectArray(data.vision_warnings),
    oaReply: typeof data.final_reply_text === "string" ? data.final_reply_text : "",
    oaSourceText: typeof data.oa_source_text === "string" ? data.oa_source_text : "",
    oaNoticeFocusText: typeof data.oa_notice_focus_text === "string" ? data.oa_notice_focus_text : "",
    oaNoticeFocusApplied: data.oa_notice_focus_applied === true,
  };
}

export function mapEventPayload(eventType: string, payload: SessionEventPayload): {
  timestamp: string;
  type: string;
  payload: Record<string, unknown>;
} {
  const rawPayload =
    payload.payload && typeof payload.payload === "object"
      ? payload.payload
      : (payload as unknown as Record<string, unknown>);
  return {
    timestamp: typeof payload.timestamp === "string" ? payload.timestamp : new Date().toISOString(),
    type: eventType,
    // Redact large or sensitive text before rendering stream logs.
    payload: redactLogPayload(rawPayload),
  };
}

function readCurrentStep(data: unknown): string | null {
  if (!data || typeof data !== "object") {
    return null;
  }
  const value = (data as Record<string, unknown>).current_step;
  return typeof value === "string" ? value : null;
}

function readStringField(data: unknown, key: string): string | null {
  if (!data || typeof data !== "object") {
    return null;
  }
  const value = (data as Record<string, unknown>)[key];
  return typeof value === "string" ? value : null;
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function readObjectArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item));
}

function redactLogPayload(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return redactValue(value) as Record<string, unknown>;
}

function redactValue(value: unknown): unknown {
  const sensitiveKeys = new Set(["disclosure_text", "oa_text", "content", "text", "snippet"]);

  if (typeof value === "string") {
    return truncateText(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item));
  }
  if (value && typeof value === "object") {
    const redacted: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (sensitiveKeys.has(key) && typeof item === "string") {
        redacted[key] = `<redacted len=${item.length}>`;
      } else {
        redacted[key] = redactValue(item);
      }
    }
    return redacted;
  }
  return value;
}

function truncateText(value: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= 160) {
    return normalized;
  }
  return `${normalized.slice(0, 160)}... [truncated len=${normalized.length}]`;
}
