export type GlobalTab = "home" | "draft" | "oa" | "compare" | "polish" | "settings";

export interface WorkflowStepConfig {
  id: string;
  label: string;
}

export interface WorkflowOutputConfig {
  nodeId: string;
  title: string;
  valueKey: string;
}

const OUTPUT_KEY_ALIASES: Partial<Record<Exclude<GlobalTab, "home" | "settings">, Record<string, string[]>>> = {
  draft: {
    specification: [
      "specification",
      "approved_specification",
      "application_specification",
      "final_specification",
      "specification_text",
    ],
  },
  polish: {
    diagnostic_report: ["diagnostic_report"],
    synergy_vault: ["synergy_feature_vault"],
    claim_architecture_plan: ["claim_architecture_plan", "reconstructed_claim_tree"],
    amplified_specification: ["amplified_specification", "specification_amplification_report"],
    adversarial_review_report: ["adversarial_review_report"],
  },
};

export const WORKFLOW_STEPS: Record<Exclude<GlobalTab, "home" | "settings">, WorkflowStepConfig[]> = {
  draft: [
    { id: "extract_tech_node", label: "技术要点提取" },
    { id: "drawing_analyze_node", label: "附图分析" },
    { id: "draft_claims_node", label: "权利要求生成" },
    { id: "traceability_check_node", label: "可追溯性检查" },
    { id: "human_review_node", label: "权利要求确认" },
    { id: "write_spec_node", label: "说明书撰写" },
    { id: "logic_review_node", label: "逻辑审查" },
  ],
  oa: [
    { id: "application_baseline_agent", label: "本案分析" },
    { id: "oa_parser_node", label: "审查意见分析" },
    { id: "multimodal_prior_art_agent", label: "对比文件核验" },
    { id: "concession_and_gap_node", label: "修改方向确认" },
    { id: "fallback_feature_miner_node", label: "说明书特征挖掘" },
    { id: "prior_art_stress_tester_node", label: "候选特征审查" },
    { id: "strategy_decision_node", label: "答复策略" },
    { id: "claim_amendment_agent", label: "权利要求修改" },
    { id: "argument_writer_agent", label: "答辩正文" },
    { id: "spec_update_agent", label: "说明书修改" },
    { id: "response_traceability_node", label: "逻辑审查" },
  ],
  compare: [
    { id: "multimodal_draft_parser_node", label: "申请文件分析" },
    { id: "multimodal_prior_art_node", label: "对比文件分析" },
    { id: "multimodal_matrix_comparison_node", label: "特征比对" },
    { id: "risk_assessment_node", label: "风险评估" },
    { id: "amendment_suggestion_node", label: "修改建议" },
  ],
  polish: [
    { id: "multimodal_diagnostic_analyzer_node", label: "申请文件分析" },
    { id: "multimodal_synergy_miner_node", label: "特征挖掘" },
    { id: "claim_architect_node", label: "权利要求润色" },
    { id: "specification_amplifier_node", label: "说明书润色" },
    { id: "multimodal_adversarial_reviewer_node", label: "逻辑审查" },
  ],
};

export const WORKFLOW_OUTPUTS: Record<Exclude<GlobalTab, "home" | "settings">, WorkflowOutputConfig[]> = {
  draft: [
    { nodeId: "extract_tech_node", title: "技术要点提取", valueKey: "tech_summary" },
    { nodeId: "drawing_analyze_node", title: "附图分析", valueKey: "drawing_map" },
    { nodeId: "draft_claims_node", title: "权利要求生成", valueKey: "claims" },
    { nodeId: "traceability_check_node", title: "可追溯性检查", valueKey: "claim_traceability" },
    { nodeId: "human_review_node", title: "权利要求确认", valueKey: "claims" },
    { nodeId: "write_spec_node", title: "说明书撰写", valueKey: "specification" },
    { nodeId: "logic_review_node", title: "逻辑审查", valueKey: "review_issues" },
  ],
  oa: [
    { nodeId: "application_baseline_agent", title: "本案分析", valueKey: "application_baseline" },
    { nodeId: "oa_parser_node", title: "审查意见分析", valueKey: "parsed_defects" },
    { nodeId: "multimodal_prior_art_agent", title: "对比文件核验", valueKey: "prior_art_targeted_report" },
    { nodeId: "concession_and_gap_node", title: "修改方向确认", valueKey: "concession_gap_report" },
    { nodeId: "fallback_feature_miner_node", title: "说明书特征挖掘", valueKey: "mined_fallback_features" },
    { nodeId: "prior_art_stress_tester_node", title: "候选特征审查", valueKey: "stress_test_report" },
    { nodeId: "strategy_decision_node", title: "答复策略", valueKey: "strategy_decision" },
    { nodeId: "claim_amendment_agent", title: "权利要求修改", valueKey: "amended_claims" },
    { nodeId: "argument_writer_agent", title: "答辩正文", valueKey: "argument_draft" },
    { nodeId: "spec_update_agent", title: "说明书修改", valueKey: "spec_update_note" },
    { nodeId: "response_traceability_node", title: "逻辑审查", valueKey: "response_traceability" },
  ],
  compare: [
    { nodeId: "multimodal_draft_parser_node", title: "申请文件分析", valueKey: "draft_baseline" },
    { nodeId: "multimodal_prior_art_node", title: "对比文件分析", valueKey: "prior_art_profiles" },
    { nodeId: "multimodal_matrix_comparison_node", title: "特征比对", valueKey: "collision_matrix" },
    { nodeId: "risk_assessment_node", title: "风险评估", valueKey: "risk_assessment_report" },
    { nodeId: "amendment_suggestion_node", title: "修改建议", valueKey: "amendment_suggestions" },
  ],
  polish: [
    { nodeId: "multimodal_diagnostic_analyzer_node", title: "申请文件分析", valueKey: "diagnostic_report" },
    { nodeId: "multimodal_synergy_miner_node", title: "特征挖掘", valueKey: "synergy_feature_vault" },
    { nodeId: "claim_architect_node", title: "权利要求润色", valueKey: "claim_architecture_plan" },
    { nodeId: "specification_amplifier_node", title: "说明书润色", valueKey: "amplified_specification" },
    { nodeId: "multimodal_adversarial_reviewer_node", title: "逻辑审查", valueKey: "adversarial_review_report" },
  ],
};

export function getWorkflowOutputValue(
  mode: Exclude<GlobalTab, "home" | "settings">,
  valueKey: string,
  data: Record<string, unknown> | null,
): unknown {
  if (!data) return null;
  const primary = data[valueKey];
  if (primary !== null && primary !== undefined) return primary;
  const aliases = OUTPUT_KEY_ALIASES[mode]?.[valueKey] ?? [];
  for (const alias of aliases) {
    const candidate = data[alias];
    if (candidate !== null && candidate !== undefined) return candidate;
  }
  return null;
}

export function getFinalTextForMode(
  mode: Exclude<GlobalTab, "home" | "settings">,
  data: Record<string, unknown> | null,
): string {
  if (!data) return "";

  const pickString = (value: unknown): string => {
    if (typeof value === "string") return value;
    if (value && typeof value === "object") {
      const text = (value as Record<string, unknown>).text;
      if (typeof text === "string") return text;
      return JSON.stringify(value, null, 2);
    }
    return "";
  };

  if (mode === "draft") {
    return pickString(data.specification) || pickString(data.claims);
  }
  if (mode === "oa") {
    return pickString(data.final_reply_text) || pickString(data.argument_draft);
  }
  if (mode === "compare") {
    return pickString(data.final_compare_report) || pickString(data.risk_assessment_report) || pickString(data.amendment_suggestions);
  }
  return pickString(data.polish_final_package) || pickString(data.optimized_claims_text) || pickString(data.optimized_specification_text);
}

