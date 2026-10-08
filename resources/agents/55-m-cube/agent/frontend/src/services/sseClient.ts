import type { SessionEventPayload } from "@/types/api";

interface SessionSSEOptions {
  baseUrl: string;
  sessionId: string;
  afterIndex?: number;
  onMessage: (eventType: string, payload: SessionEventPayload) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
}

export interface SessionSSEConnection {
  close: () => void;
}

export function connectSessionEvents(options: SessionSSEOptions): SessionSSEConnection {
  const afterIndex = options.afterIndex ?? 0;
  const baseUrl = options.baseUrl.replace(/\/+$/, "");
  const url = `${baseUrl}/api/v1/sessions/${encodeURIComponent(options.sessionId)}/events?after_index=${afterIndex}`;

  // Browser EventSource does not support custom headers; local dev relies on optional API key.
  const source = new EventSource(url);

  source.onopen = () => {
    options.onOpen?.();
  };

  source.onerror = (event) => {
    options.onError?.(event);
  };

  const forward = (eventType: string) => (event: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(event.data) as SessionEventPayload;
      options.onMessage(eventType, payload);
    } catch {
      options.onMessage(eventType, { type: eventType, payload: { raw: event.data } });
    }
  };

  source.addEventListener("node_started", forward("node_started"));
  source.addEventListener("node_finished", forward("node_finished"));
  source.addEventListener("hitl_required", forward("hitl_required"));
  source.addEventListener("session_completed", forward("session_completed"));
  source.addEventListener("session_failed", forward("session_failed"));
  source.addEventListener("session_cancelled", forward("session_cancelled"));
  source.addEventListener("heartbeat", forward("heartbeat"));
  source.addEventListener("stream_offset", forward("stream_offset"));

  return {
    close: () => source.close(),
  };
}
