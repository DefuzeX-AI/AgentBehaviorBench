import { useDocumentStore } from "@/stores/documentStore";
import { useLogStore } from "@/stores/logStore";
import { useSessionStore } from "@/stores/sessionStore";
import { beforeEach, describe, expect, test } from "vitest";

describe("Zustand stores", () => {
  beforeEach(() => {
    useSessionStore.getState().resetSession();
    useLogStore.getState().clearEvents();
    useDocumentStore.getState().reset();
  });

  test("session store updates and resets lifecycle fields", () => {
    useSessionStore.getState().setSession({
      sessionId: "s-1",
      requestId: "r-1",
      status: "running",
      currentStep: "extract_tech_node",
      visionMode: "real",
    });

    expect(useSessionStore.getState().sessionId).toBe("s-1");
    expect(useSessionStore.getState().status).toBe("running");
    expect(useSessionStore.getState().visionMode).toBe("real");

    useSessionStore.getState().resetSession();
    expect(useSessionStore.getState().sessionId).toBeNull();
    expect(useSessionStore.getState().status).toBeNull();
  });

  test("log store appends ordered events", () => {
    useLogStore.getState().appendEvent({
      timestamp: "2026-03-02T00:00:00Z",
      type: "node_started",
      payload: { node: "a" },
    });
    useLogStore.getState().appendEvent({
      timestamp: "2026-03-02T00:00:01Z",
      type: "node_finished",
      payload: { node: "a" },
    });

    const { events } = useLogStore.getState();
    expect(events).toHaveLength(2);
    expect(events[0].type).toBe("node_started");
    expect(events[1].type).toBe("node_finished");
  });

  test("document store keeps claims/spec/oa draft state", () => {
    useDocumentStore.getState().setClaims({
      claims: [
        {
          claim_number: 1,
          claim_type: "independent",
          depends_on: [],
          preamble: "A system",
          transition: "comprising:",
          elements: ["a controller", "a sensor"],
          full_text: "A system comprising: a controller; a sensor.",
        },
      ],
    });
    useDocumentStore.getState().setSpecification({
      title: "t",
      technical_field: "field text long enough",
      background_art: "background text long enough for validation checks in tests",
      invention_content: {
        technical_problem: "problem text long enough for test validation",
        technical_solution: "solution text long enough for schema validation in test payload and sample usage",
        beneficial_effects: "effects text long enough for schema validation",
      },
      drawings_description: "draw",
      detailed_implementation: {
        introductory_boilerplate: "为了使本发明的目的更加清楚，以下结合实施例说明。",
        overall_architecture: "overall architecture text long enough for schema validation in frontend sample payload",
        component_details: [
          {
            feature_name: "module10",
            structure_and_connection: "connection text long enough for schema validation in test sample",
            working_principle: "principle text long enough for schema validation in test sample",
          },
        ],
        workflow_description: "workflow text long enough for schema validation in frontend sample payload",
        alternative_embodiments: "alternative embodiments text long enough for schema validation",
      },
    });
    useDocumentStore.getState().setDrawingMap({ figures: [], overall_notes: "ok", warnings: [] });
    useDocumentStore.getState().setVisualReport({ conclusion: "diff" });
    useDocumentStore.getState().setOaReply("reply");

    const state = useDocumentStore.getState();
    expect(state.claims).not.toBeNull();
    expect(state.specification).not.toBeNull();
    expect(state.drawingMap).not.toBeNull();
    expect(state.visualReport).not.toBeNull();
    expect(state.oaReply).toBe("reply");
  });
});
