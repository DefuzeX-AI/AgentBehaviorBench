import { create } from "zustand";

interface DocumentState {
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
  setDisclosureText: (disclosureText: string) => void;
  setDisclosureImagesMeta: (items: Array<Record<string, unknown>>) => void;
  setClaims: (claims: Record<string, unknown>) => void;
  setDrawingMap: (drawingMap: Record<string, unknown> | null) => void;
  setClaimTraceability: (claimTraceability: Record<string, unknown>) => void;
  setSpecification: (specification: Record<string, unknown>) => void;
  setVisualReport: (visualReport: Record<string, unknown> | null) => void;
  setApplicationImagesMeta: (items: Array<Record<string, unknown>>) => void;
  setPriorArtImagesMeta: (items: Array<Record<string, unknown>>) => void;
  setVisionWarnings: (items: Array<Record<string, unknown>>) => void;
  setOaReply: (oaReply: string) => void;
  setOaSourceText: (oaSourceText: string) => void;
  setOaNoticeFocusText: (oaNoticeFocusText: string) => void;
  setOaNoticeFocusApplied: (oaNoticeFocusApplied: boolean) => void;
  reset: () => void;
}

export const useDocumentStore = create<DocumentState>((set) => ({
  disclosureText: "",
  disclosureImagesMeta: [],
  claims: null,
  drawingMap: null,
  claimTraceability: null,
  specification: null,
  visualReport: null,
  applicationImagesMeta: [],
  priorArtImagesMeta: [],
  visionWarnings: [],
  oaReply: "",
  oaSourceText: "",
  oaNoticeFocusText: "",
  oaNoticeFocusApplied: false,
  setDisclosureText: (disclosureText) => set({ disclosureText }),
  setDisclosureImagesMeta: (disclosureImagesMeta) => set({ disclosureImagesMeta }),
  setClaims: (claims) => set({ claims }),
  setDrawingMap: (drawingMap) => set({ drawingMap }),
  setClaimTraceability: (claimTraceability) => set({ claimTraceability }),
  setSpecification: (specification) => set({ specification }),
  setVisualReport: (visualReport) => set({ visualReport }),
  setApplicationImagesMeta: (applicationImagesMeta) => set({ applicationImagesMeta }),
  setPriorArtImagesMeta: (priorArtImagesMeta) => set({ priorArtImagesMeta }),
  setVisionWarnings: (visionWarnings) => set({ visionWarnings }),
  setOaReply: (oaReply) => set({ oaReply }),
  setOaSourceText: (oaSourceText) => set({ oaSourceText }),
  setOaNoticeFocusText: (oaNoticeFocusText) => set({ oaNoticeFocusText }),
  setOaNoticeFocusApplied: (oaNoticeFocusApplied) => set({ oaNoticeFocusApplied }),
  reset: () =>
    set({
      disclosureText: "",
      disclosureImagesMeta: [],
      claims: null,
      drawingMap: null,
      claimTraceability: null,
      specification: null,
      visualReport: null,
      applicationImagesMeta: [],
      priorArtImagesMeta: [],
      visionWarnings: [],
      oaReply: "",
      oaSourceText: "",
      oaNoticeFocusText: "",
      oaNoticeFocusApplied: false,
    }),
}));
