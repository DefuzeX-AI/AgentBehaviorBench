import { ApiClient, ApiClientError } from "@/services/apiClient";
import { afterEach, describe, expect, test, vi } from "vitest";

describe("apiClient integration with mocked backend", () => {
  const client = new ApiClient({ baseUrl: "http://127.0.0.1:8000" });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("startDraft returns envelope on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          request_id: "r-1",
          session_id: "s-1",
          status: "waiting_human",
          data: { current_step: "human_review_node" },
          error: null,
        }),
      })),
    );

    const result = await client.startDraft({
      idempotency_key: "idem-1",
      disclosure_text: "disclosure",
      metadata: {},
    });

    expect(result.session_id).toBe("s-1");
    expect(result.status).toBe("waiting_human");
  });

  test("maps ApiEnvelope errors into ApiClientError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 409,
        json: async () => ({
          request_id: "r-2",
          session_id: "s-2",
          status: "failed",
          data: null,
          error: {
            code: "E409_HITL_STATE_CONFLICT",
            message: "Session is not waiting for human review.",
            details: {},
            retryable: false,
          },
        }),
      })),
    );

    await expect(
      client.continueDraft({
        session_id: "s-2",
        approved_claims: {},
      }),
    ).rejects.toMatchObject({
      code: "E409_HITL_STATE_CONFLICT",
      httpStatus: 409,
    });
  });

  test("uploadFile returns parsed file payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          request_id: "r-3",
          session_id: "f-1",
          status: "completed",
          data: {
            file_id: "f-1",
            filename: "demo.txt",
            content_type: "text/plain",
            size_bytes: 12,
          },
          error: null,
        }),
      })),
    );

    const file = new File(["hello world"], "demo.txt", { type: "text/plain" });
    const result = await client.uploadFile(file, "draft_disclosure");
    expect(result.file_id).toBe("f-1");
    expect(result.filename).toBe("demo.txt");
  });
});
