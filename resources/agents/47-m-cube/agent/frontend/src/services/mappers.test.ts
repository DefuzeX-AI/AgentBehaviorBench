import { mapDocumentEnvelope, mapSessionEnvelope } from "@/services/mappers";
import { describe, expect, test } from "vitest";

describe("mappers multimodal fields", () => {
  test("mapSessionEnvelope reads vision mode and session data", () => {
    const mapped = mapSessionEnvelope({
      request_id: "r-1",
      session_id: "s-1",
      status: "running",
      data: {
        current_step: "drawing_analyze_node",
        llm_mode: "real",
        llm_runtime: { provider: "openai" },
        vision_mode: "real",
      },
      error: null,
    });
    expect(mapped.currentStep).toBe("drawing_analyze_node");
    expect(mapped.llmMode).toBe("real");
    expect(mapped.visionMode).toBe("real");
    expect(mapped.llmRuntime).toEqual({ provider: "openai" });
  });

  test("mapDocumentEnvelope reads multimodal payload fields", () => {
    const mapped = mapDocumentEnvelope({
      request_id: "r-2",
      session_id: "s-2",
      status: "waiting_human",
      data: {
        disclosure_text: "demo",
        disclosure_images_meta: [{ image_id: "img-1" }],
        drawing_map: { figures: [], overall_notes: "ok", warnings: [] },
        visual_report: { conclusion: "diff found" },
        application_images_meta: [{ image_id: "a-1" }],
        prior_art_images_meta: [{ image_id: "p-1" }],
        vision_warnings: [{ code: "VISION_FALLBACK" }],
      },
      error: null,
    });
    expect(mapped.disclosureText).toBe("demo");
    expect(mapped.disclosureImagesMeta).toHaveLength(1);
    expect(mapped.drawingMap?.overall_notes).toBe("ok");
    expect(mapped.visualReport?.conclusion).toBe("diff found");
    expect(mapped.applicationImagesMeta).toHaveLength(1);
    expect(mapped.priorArtImagesMeta).toHaveLength(1);
    expect(mapped.visionWarnings).toHaveLength(1);
  });
});
