type WorkflowMode = "draft" | "oa" | "compare" | "polish" | null;

interface FlowOutputsPanelProps {
  mode: WorkflowMode;
  data: Record<string, unknown> | null;
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function Section({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 text-xs text-slate-800">
        {renderValue(value)}
      </pre>
    </div>
  );
}

export function FlowOutputsPanel({ mode, data }: FlowOutputsPanelProps) {
  if (!data) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">流程输出</h2>
        <p className="mt-2 text-sm text-slate-500">当前暂无流程输出。</p>
      </section>
    );
  }

  const draftSections = [
    { key: "tech_summary", title: "技术要点提取输出" },
    { key: "claims", title: "权利要求输出" },
    { key: "drawing_map", title: "附图分析输出" },
    { key: "claim_traceability", title: "可追溯性检查输出" },
    { key: "specification", title: "说明书撰写输出" },
    { key: "vision_warnings", title: "视觉告警" },
    { key: "review_issues", title: "逻辑审校输出" },
  ];

  const oaSections = [
    { key: "application_baseline", title: "1. 本案基线（application_baseline_node）" },
    { key: "parsed_defects", title: "2. 审查意见解析（oa_parser_node）" },
    { key: "prior_art_targeted_report", title: "3. 定向图文核验（multimodal_prior_art_agent_node）" },
    { key: "concession_gap_report", title: "4. 差距分析（concession_and_gap_node）" },
    { key: "mined_fallback_features", title: "5. 后备特征挖掘（fallback_feature_miner_node）" },
    { key: "stress_test_report", title: "6. 对比文件压力测试（prior_art_stress_tester_node）" },
    { key: "strategy_decision", title: "7. 策略决策（strategy_decision_node）" },
    { key: "amended_claims", title: "8. 权利要求修改（claim_amendment_node）" },
    { key: "argument_draft", title: "9. 答辩正文（argument_writer_node）" },
    { key: "spec_update_note", title: "10. 说明书微调（spec_update_node）" },
    { key: "response_traceability", title: "11. 终审合规（response_traceability_node）" },
  ];

  const compareSections = [
    { key: "draft_baseline", title: "1. 本案多模态基线锚定（multimodal_draft_parser_node）" },
    { key: "prior_art_profiles", title: "2. 现有专利视觉解剖（multimodal_prior_art_node）" },
    { key: "targeted_reading_audit", title: "2.1 定向阅读审计（multimodal_prior_art_node）" },
    { key: "feature_collision_matrix", title: "3. 多模态特征矩阵碰撞（multimodal_matrix_comparison_node）" },
    { key: "prior_art_targeted_report", title: "3.1 图文综合核验结论（multimodal_matrix_comparison_node）" },
    { key: "risk_report", title: "4. 差异与风险评估（risk_assessment_node）" },
    { key: "amendment_suggestions", title: "5. 规避与修改建议（amendment_suggestion_node）" },
    { key: "final_compare_report", title: "最终结论（compare）" },
  ];

  const polishSections = [
    { key: "diagnostic_report", title: "1. 初稿视觉与文本诊断（multimodal_diagnostic_analyzer_node）" },
    { key: "synergy_feature_vault", title: "2. 多模态深层机理挖掘（multimodal_synergy_miner_node）" },
    { key: "claim_architecture_plan", title: "3. 权利要求架构重构（claim_architect_node）" },
    { key: "optimized_claims_text", title: "3.1 优化后权利要求全文" },
    { key: "amplified_specification", title: "4. 说明书血肉丰满（specification_amplifier_node）" },
    { key: "optimized_specification_text", title: "4.1 优化后说明书全文" },
    { key: "adversarial_review_report", title: "5. 多模态红蓝对抗终审（multimodal_adversarial_reviewer_node）" },
    { key: "polish_final_package", title: "最终定稿（polish）" },
  ];

  const sections =
    mode === "oa"
      ? oaSections
      : mode === "compare"
        ? compareSections
        : mode === "polish"
          ? polishSections
          : draftSections;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">流程输出</h2>
      <p className="mt-1 text-xs text-slate-500">按节点顺序展示当前会话输出。</p>
      <div className="mt-3 space-y-3">
        {sections.map((item) => (
          <Section key={item.key} title={item.title} value={data[item.key]} />
        ))}
      </div>
    </section>
  );
}
