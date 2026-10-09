import { useState } from "react";
import type { GlobalTab } from "@/components/workflow/workflowConfig";

interface NodeStageRendererProps {
  mode: GlobalTab;
  nodeId: string;
  nodeTitle: string;
  value: unknown;
  sessionData: Record<string, unknown> | null;
  showSpecReviewActions?: boolean;
  busy?: boolean;
  onExecuteRevision?: (instruction: string) => void;
  onFinish?: () => void;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

function toText(value: unknown): string {
  if (value === null || value === undefined) return "当前节点暂无输出。";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function readRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function readArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function readNum(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function extractFigureIndex(value: unknown): number | null {
  const text = String(value ?? "");
  const m = text.match(/(\d{1,3})/);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

function imageIdFromMeta(item: Record<string, unknown>): string | null {
  const direct = item.image_id;
  if (typeof direct === "string" && direct.trim()) return direct.trim();
  const source = item.source_path;
  if (typeof source === "string" && source.trim()) {
    const filename = source.replace(/\\/g, "/").split("/").pop() ?? "";
    const dot = filename.lastIndexOf(".");
    return (dot > 0 ? filename.slice(0, dot) : filename) || null;
  }
  return null;
}

function pickFigureImageId(
  figure: Record<string, unknown>,
  idx: number,
  metas: Array<Record<string, unknown>>,
): string | null {
  if (metas.length === 0) return null;
  const figureIdx = extractFigureIndex(figure.figure_id ?? figure.figure_label) ?? idx + 1;

  const byPage = metas.find((m) => {
    const pageIdx = readNum(m.page_index);
    return pageIdx !== null && pageIdx + 1 === figureIdx;
  });
  if (byPage) return imageIdFromMeta(byPage);

  const byHint = metas.find((m) => {
    const hint = String(m.caption_hint ?? "");
    return hint.includes(`page=${figureIdx}`) || hint.includes(`图${figureIdx}`);
  });
  if (byHint) return imageIdFromMeta(byHint);

  return imageIdFromMeta(metas[idx] ?? {}) ?? null;
}

function pickFigureImageIdStrictByLabel(
  figureLabel: string,
  metas: Array<Record<string, unknown>>,
): string | null {
  if (metas.length === 0) return null;
  const figureIdx = extractFigureIndex(figureLabel);
  if (figureIdx === null) return null;

  const byPage = metas.find((m) => {
    const pageIdx = readNum(m.page_index);
    return pageIdx !== null && pageIdx + 1 === figureIdx;
  });
  if (byPage) return imageIdFromMeta(byPage);

  const byHint = metas.find((m) => {
    const hint = String(m.caption_hint ?? "");
    return hint.includes(`page=${figureIdx}`) || hint.includes(`图${figureIdx}`) || hint.includes(`Fig.${figureIdx}`);
  });
  if (byHint) return imageIdFromMeta(byHint);

  const bySourceName = metas.find((m) => {
    const source = String(m.source_path ?? "").replace(/\\/g, "/");
    return new RegExp(`(?:^|[^\\d])${figureIdx}(?:[^\\d]|$)`).test(source);
  });
  if (bySourceName) return imageIdFromMeta(bySourceName);

  return null;
}

function JsonFallback({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[58vh] overflow-auto p-2 text-xs leading-relaxed text-gray-700">
      {toText(value)}
    </pre>
  );
}

function OaClaimsDiff({ sessionData }: { sessionData: Record<string, unknown> | null }) {
  const before = sessionData?.claims ?? sessionData?.original_claims ?? null;
  const after = sessionData?.amended_claims ?? null;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">修改前</h4>
        <pre className="mt-2 max-h-[48vh] overflow-auto border-y border-gray-200 p-3 text-xs text-gray-700">{toText(before)}</pre>
      </section>
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">修改后</h4>
        <pre className="mt-2 max-h-[48vh] overflow-auto border-y border-gray-200 p-3 text-xs text-gray-700">{toText(after)}</pre>
      </section>
    </div>
  );
}

function CompareRiskMatrix({ value }: { value: unknown }) {
  const report = readRecord(value);
  const claims = readArray(report?.claim_assessments);
  if (!report) return <JsonFallback value={value} />;

  return (
    <div className="space-y-4">
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">全局风险摘要</h4>
        <p className="mt-2 text-sm text-gray-700">{toText(report.global_risk_summary)}</p>
      </section>
      <section className="overflow-auto border-y border-gray-200">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-3 py-2">权项</th>
              <th className="px-3 py-2">新颖性风险</th>
              <th className="px-3 py-2">创造性风险</th>
              <th className="px-3 py-2">突破口</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((item, idx) => {
              const row = readRecord(item) ?? {};
              return (
                <tr className="border-t border-gray-100" key={`risk-${idx}`}>
                  <td className="px-3 py-2 text-gray-700">{toText(row.claim_number)}</td>
                  <td className="px-3 py-2 text-gray-700">{toText(row.novelty_risk)}</td>
                  <td className="px-3 py-2 text-gray-700">{toText(row.inventiveness_risk)}</td>
                  <td className="px-3 py-2 text-gray-700">{toText(row.breakthrough_point)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">修改战略</h4>
        <p className="mt-2 text-sm text-gray-700">{toText(report.strategic_amendment_direction)}</p>
      </section>
    </div>
  );
}

function CompareCollisionMatrix({ value }: { value: unknown }) {
  const matrix = readRecord(value);
  if (!matrix) return <JsonFallback value={value} />;
  const claimRows = readArray(matrix.prior_art_targeted_report);

  return (
    <div className="space-y-4">
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">全局结论</h4>
        <p className="mt-2 text-sm text-gray-700">{toText(matrix.global_conclusion)}</p>
      </section>
      {claimRows.map((claim, idx) => {
        const claimObj = readRecord(claim) ?? {};
        const features = readArray(claimObj.feature_collisions);
        return (
          <section className="p-3" key={`claim-collision-${idx}`}>
            <h4 className="text-sm font-semibold text-gray-800">
              权利要求 {toText(claimObj.claim_number)} · {toText(claimObj.claim_safety_status)}
            </h4>
            <div className="mt-2 overflow-auto border-y border-gray-200">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-2 py-2">特征ID</th>
                    <th className="px-2 py-2">文本证据</th>
                    <th className="px-2 py-2">视觉证据</th>
                    <th className="px-2 py-2">部件匹配</th>
                    <th className="px-2 py-2">关系匹配</th>
                    <th className="px-2 py-2">判定</th>
                  </tr>
                </thead>
                <tbody>
                  {features.map((feature, fIdx) => {
                    const f = readRecord(feature) ?? {};
                    return (
                      <tr className="border-t border-gray-100" key={`feature-${idx}-${fIdx}`}>
                        <td className="px-2 py-2">{toText(f.feature_id)}</td>
                        <td className="px-2 py-2">{toText(f.text_evidence)}</td>
                        <td className="px-2 py-2">{toText(f.visual_evidence)}</td>
                        <td className="px-2 py-2">{toText(f.component_match_status)}</td>
                        <td className="px-2 py-2">{toText(f.relationship_match_status)}</td>
                        <td className="px-2 py-2">{toText(f.disclosure_status)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}

function OaArgumentCards({ value }: { value: unknown }) {
  const draft = readRecord(value);
  if (!draft) return <JsonFallback value={value} />;
  const details = readArray(draft.detailed_technical_differences);
  const effects = readArray(draft.unexpected_effects);

  return (
    <div className="space-y-4">
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">修改说明</h4>
        <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700">{toText(draft.amendment_statement)}</p>
      </section>
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">审查逻辑反驳</h4>
        <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700">{toText(draft.examiner_logic_refutation)}</p>
      </section>
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">技术差异要点</h4>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-700">
          {details.map((item, idx) => (
            <li key={`diff-${idx}`}>{toText(item)}</li>
          ))}
        </ul>
      </section>
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">预料不到技术效果</h4>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-700">
          {effects.map((item, idx) => (
            <li key={`eff-${idx}`}>{toText(item)}</li>
          ))}
        </ul>
      </section>
      <section className="p-3">
        <h4 className="text-sm font-semibold text-gray-800">最终答复正文</h4>
        <pre className="mt-2 max-h-[36vh] overflow-auto whitespace-pre-wrap border-y border-gray-200 p-3 text-xs text-gray-700">{toText(draft.final_reply_text)}</pre>
      </section>
    </div>
  );
}

function ArgumentWriterView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <div className="p-8 text-center text-gray-500">加载答辩正文定稿数据中...</div>;

  const details = readArray(data.detailed_technical_differences);
  const effects = readArray(data.unexpected_effects);
  const finalReplyText = String(data.final_reply_text ?? "");
  const replyTextArray = finalReplyText
    ? finalReplyText
        .split(/\r?\n/)
        .map((p) => p.trim())
        .filter((p) => p !== "")
    : [];

  const renderSmartIllustration = (textRaw: unknown) => {
    const text = String(textRaw ?? "");
    if (!text) return null;

    let imageTag: string | null = null;
    if (text.includes("流体腔") && text.includes("密封唇")) {
      imageTag = "流体腔-密封唇协同机理示意";
    } else if (text.includes("挡环") && text.includes("垂直面")) {
      imageTag = "挡环与垂直面约束关系示意";
    } else if (text.includes("锯齿状缓冲层")) {
      imageTag = "锯齿状缓冲层受力路径示意";
    }

    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">答复正文</h2>

        <div className="max-w-4xl border-l-[3px] border-gray-900 py-1 pl-5">
          <strong className="mb-3 block text-[14.5px] font-bold uppercase tracking-widest text-gray-900">
            修改基础与合规确认
          </strong>
          <p className="font-serif text-[15.5px] italic leading-[1.9] text-gray-800 text-justify">{toText(data.amendment_statement)}</p>
        </div>
      </div>

      <div className="mb-24 space-y-16">
        <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          答复思路
        </h3>

        <div className="pl-2">
          <div className="text-[15.5px] leading-[1.9] text-gray-900 text-justify">
            <strong className="mr-2 text-gray-900">核心答复逻辑：</strong>
            {toText(data.examiner_logic_refutation)}
          </div>
        </div>
      </div>

      <div className="mb-24 space-y-16">
        <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          技术特征对比
        </h3>

        <div className="space-y-16 pl-2">
          <div className="space-y-10">
            {details.map((diffRaw, idx) => {
              const diff = toText(diffRaw);
              const parts = diff.split("：");
              const title = parts.length > 1 ? parts[0] : `差异特征 ${idx + 1}`;
              const content = parts.length > 1 ? parts.slice(1).join("：") : diff;

              return (
                <div className="space-y-3" key={`oa-final-diff-${idx}`}>
                  <div className="text-[15.5px] leading-[1.8] text-gray-800 text-justify">
                    <strong className="mr-2 border-b border-gray-300 pb-0.5 text-gray-900">
                      {title}
                    </strong>
                    <span className="mt-2 block">{content}</span>
                  </div>
                  {renderSmartIllustration(title)}
                </div>
              );
            })}
          </div>

          <div className="mt-10 border-l-2 border-gray-300 pl-5">
            <strong className="mb-3 block text-[15px] text-gray-900">整体非显而易见性论述：</strong>
            <p className="font-serif text-[15.5px] leading-[1.9] text-gray-800 text-justify">{toText(data.non_obviousness_argument)}</p>
          </div>
        </div>
      </div>

      <div className="mb-24 space-y-12">
        <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          预料不到的技术效果论述
        </h3>

        <div className="space-y-6 pl-2">
          {effects.map((effectRaw, idx) => (
            <div className="flex items-start gap-4" key={`oa-final-effect-${idx}`}>
              <p className="text-[15.5px] leading-[1.8] text-gray-800 text-justify">{toText(effectRaw)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="pt-10">
        <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <h3 className="text-xl font-bold uppercase tracking-widest text-gray-900">答复正文</h3>
          <button className="rounded border border-gray-300 px-4 py-1.5 text-[13px] font-bold text-gray-600 transition-colors hover:border-gray-900 hover:text-gray-900">
            一键复制陈述书全文
          </button>
        </div>

        <div className="border-y border-gray-300 bg-gray-50/30 px-4 py-16 sm:px-12">
          <div className="mx-auto max-w-4xl space-y-6">
            {replyTextArray.map((para, idx) => {
              const isGreetingOrSignoff =
                para.length < 30 &&
                (para.includes("：") || para.includes("此致") || para.includes("敬礼") || para.includes("申请人") || para.includes("代理机构") || para.includes("年"));

              return (
                <p
                  className={`font-serif text-[16px] leading-[2.4] text-gray-900 ${isGreetingOrSignoff ? "text-left font-bold" : "indent-8 text-justify"}`}
                  key={`oa-reply-para-${idx}`}
                >
                  {para}
                </p>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function ApplicationBaselineView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const claimsTree = readArray(data.claims_tree);
  const specFeatureIndex = readArray(data.spec_feature_index);

  return (
    <div className="mx-auto w-full max-w-6xl space-y-16 pb-24">
      <div className="mt-4 border-b border-gray-200 pb-6">
        <h3 className="text-3xl font-bold text-gray-900">本案分析</h3>
      </div>

      {claimsTree.length > 0 ? (
        <section className="space-y-8">
          <h4 className="flex items-center gap-2 border-l-4 border-blue-600 pl-4 text-xl font-bold text-gray-900">
            权利要求树特征拆解
          </h4>

          <div className="space-y-10 pl-2">
            {claimsTree.map((claimItem, idx) => {
              const claim = readRecord(claimItem) ?? {};
              const features = readArray(claim.features);
              const claimType = String(claim.claim_type ?? "");
              const dependsOn = readArray(claim.depends_on);
              const isIndependent = claimType === "independent" || claim.is_independent === true;

              return (
                <article className="border-t border-gray-100 pt-8 first:border-0 first:pt-0" key={`oa-baseline-claim-${idx}`}>
                  <div className="mb-5 flex items-center gap-3">
                    <span className="text-xl font-bold text-gray-900">权利要求 {toText(claim.claim_number ?? idx + 1)}</span>
                    {isIndependent ? (
                      <span className="rounded border-2 border-gray-800 px-2 py-0.5 text-[12px] font-bold tracking-wider text-gray-800">
                        独立权利要求
                      </span>
                    ) : (
                      <span className="rounded border border-gray-300 px-2 py-0.5 text-[12px] font-medium text-gray-500">
                        引用权 {dependsOn.length > 0 ? dependsOn.map((d) => toText(d)).join(", ") : "-"}
                      </span>
                    )}
                  </div>

                  {features.length > 0 ? (
                    <ul className="space-y-3">
                      {features.map((featureItem, fIdx) => {
                        const feature = readRecord(featureItem) ?? {};
                        return (
                          <li className="flex items-start gap-4" key={`oa-feature-${idx}-${fIdx}`}>
                            <span className="mt-0.5 w-8 shrink-0 select-none text-right font-mono text-[14px] font-bold text-blue-600">
                              {toText(feature.feature_id ?? `${claim.claim_number ?? idx + 1}.${fIdx + 1}`)}
                            </span>
                            <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                              {toText(feature.feature_text ?? feature.verbatim_text ?? feature.text)}
                            </p>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="text-[15px] leading-relaxed text-gray-600">{toText(claim)}</p>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {specFeatureIndex.length > 0 ? (
        <section className="space-y-8">
          <div className="flex items-end justify-between border-l-4 border-blue-600 pl-4">
            <h4 className="text-xl font-bold text-gray-900">说明书特征与部件</h4>
            <span className="text-sm text-gray-500">
              共提取 <span className="font-bold text-gray-800">{specFeatureIndex.length}</span> 个核心部件/步骤
            </span>
          </div>

          <div className="grid grid-cols-1 gap-x-12 gap-y-10 pl-2 lg:grid-cols-2">
            {specFeatureIndex.map((item, idx) => {
              const feature = readRecord(item) ?? {};
              const refNo = String(feature.reference_numeral ?? "").trim();
              const source = String(feature.source_paragraph ?? feature.source_location ?? "").trim();
              const alt = String(feature.alternative_embodiments ?? "").trim();

              return (
                <article className="border-t border-gray-100 pt-6" key={`oa-spec-feature-${idx}`}>
                  <div className="mb-3 flex items-center gap-3">
                    <h5 className="text-[17px] font-bold text-gray-900">{toText(feature.component_or_step_name ?? feature.feature_name)}</h5>
                    {refNo && refNo !== "未提供" && refNo !== "无" ? (
                      <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-[13px] font-bold text-gray-600">{refNo}</span>
                    ) : null}
                    {source && source !== "未提供" ? (
                      <span className="ml-auto text-[12px] italic text-gray-400">溯源: {source}</span>
                    ) : null}
                  </div>

                  <div className="space-y-3">
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-800">详述:</span>
                      {toText(feature.detailed_description ?? feature.verbatim_quote ?? feature.description)}
                    </p>
                    {alt && alt !== "未提供" && alt !== "无" ? (
                      <p className="text-[14px] leading-relaxed text-gray-500 text-justify">
                        <span className="mr-2 select-none font-semibold text-gray-600">替代方案:</span>
                        {alt}
                      </p>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {(claimsTree.length === 0 && specFeatureIndex.length === 0) ? <JsonFallback value={value} /> : null}
    </div>
  );
}

function OaParserView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const root = readRecord(value);
  if (!root && !Array.isArray(value)) return <JsonFallback value={value} />;

  const defects = (() => {
    if (root) {
      const byField = readArray(root.defects);
      if (byField.length > 0) return byField;
      const byItems = readArray(root.items);
      if (byItems.length > 0) return byItems;
    }
    return Array.isArray(value) ? value : [];
  })();
  const summary = root?.overall_summary ?? root?.summary ?? "";
  const priorMetas = readArray(sessionData?.prior_art_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );
  const getEvidenceImageUrlPlaceholder = (labelRaw: unknown): string => {
    const label = String(labelRaw ?? "Fig.");
    const cleanLabel = label.replace("附", "");
    return `https://dummyimage.com/600x400/ffffff/9ca3af.png&text=Prior+Art+${encodeURIComponent(cleanLabel)}+Wireframe`;
  };
  const extractFigureLabelsFromCitedText = (valueRaw: unknown): string[] => {
    const raw = String(valueRaw ?? "");
    if (!raw) return [];
    const result: string[] = [];
    const rangeRegex = /(?:附图|图)\s*(\d+)\s*[-~]\s*(\d+)/g;
    let rangeMatch: RegExpExecArray | null = rangeRegex.exec(raw);
    while (rangeMatch) {
      const a = Number(rangeMatch[1]);
      const b = Number(rangeMatch[2]);
      if (Number.isFinite(a) && Number.isFinite(b)) {
        const lo = Math.max(1, Math.min(a, b));
        const hi = Math.min(50, Math.max(a, b));
        for (let i = lo; i <= hi; i += 1) result.push(`图${i}`);
      }
      rangeMatch = rangeRegex.exec(raw);
    }
    const single = raw.match(/(?:附图|图)\s*(\d{1,3})/g) ?? [];
    for (const token of single) {
      const m = token.match(/(\d{1,3})/);
      if (m) result.push(`图${m[1]}`);
    }
    return Array.from(new Set(result));
  };
  const renderOutlinedTag = (text: string, isHighlight = false) => (
    <span
      className={`rounded border px-2.5 py-0.5 text-[12.5px] tracking-wide ${
        isHighlight ? "border-gray-800 font-bold text-gray-900" : "border-gray-300 font-medium text-gray-600"
      }`}
    >
      {text}
    </span>
  );

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">审查意见分析</h2>
        {summary && toText(summary) !== "未提供" ? (
          <div className="max-w-4xl text-[15.5px] leading-[1.8] text-gray-800 text-justify">
            <strong className="text-gray-900">全局审查结论综述：</strong>
            {toText(summary)}
          </div>
        ) : null}
      </div>

      <div className="space-y-24">
        {defects.map((item, dIdx) => {
          const defect = readRecord(item) ?? {};
          const rejectedClaims = readArray(defect.rejected_claims).map((x) => toText(x));
          const citedDocs = readArray(defect.main_cited_docs).map((x) => toText(x));
          const mappings = readArray(defect.feature_mappings);
          const motivation = String(defect.combination_motivation ?? "").trim();
          return (
            <div key={`oa-defect-${dIdx}`}>
              <div className="mb-10 flex flex-col gap-5 border-b border-gray-200 pb-4 sm:flex-row sm:items-end">
                <h3 className="text-2xl font-bold tracking-tight text-gray-900">{toText(defect.defect_type)}</h3>

                <div className="mb-0.5 flex flex-wrap items-center gap-2">
                  <span className="mr-1 text-[13px] font-bold text-gray-500">驳回权项：</span>
                  {rejectedClaims.map((claimNum) => (
                    <span key={`claim-${dIdx}-${claimNum}`}>{renderOutlinedTag(`Claim ${claimNum}`)}</span>
                  ))}

                  <span className="ml-4 mr-1 text-[13px] font-bold text-gray-500">主引证文件：</span>
                  {citedDocs.map((doc) => (
                    <span key={`doc-${dIdx}-${doc}`}>{renderOutlinedTag(doc, true)}</span>
                  ))}
                </div>
              </div>

              {motivation && motivation !== "无" && motivation !== "未提供" ? (
                <div className="mb-16 pl-2">
                  <strong className="mb-3 block text-[15.5px] text-gray-900">审查意见：</strong>
                  <div className="border-l-[3px] border-gray-900 py-1 pl-5">
                    <p className="font-serif text-[15.5px] italic leading-[1.8] text-gray-800 text-justify">{motivation}</p>
                  </div>
                </div>
              ) : null}

              <div className="pl-2">
                <strong className="mb-10 block border-b border-gray-100 pb-2 text-[16px] uppercase tracking-widest text-gray-900">
                  驳回逻辑
                </strong>

                <div className="space-y-16">
                  {mappings.map((mappingItem, mIdx) => {
                    const mapping = readRecord(mappingItem) ?? {};
                    const priorArtDoc = toText(mapping.prior_art_doc);
                    const textSource = toText(
                      mapping.prior_art_text_disclosure ??
                        mapping.prior_art_text ??
                        mapping.text_evidence ??
                        mapping.cited_paragraphs,
                    );
                    const citedFigureText = toText(mapping.cited_figures ?? mapping.prior_art_visual_disclosure ?? mapping.visual_evidence);
                    const figureLabels = extractFigureLabelsFromCitedText(citedFigureText);
                    const metasForDoc = priorMetas.filter((m) => {
                      const hint = String(m.caption_hint ?? "");
                      return hint.includes(priorArtDoc) || hint.toUpperCase().includes(priorArtDoc.toUpperCase());
                    });
                    const metasPool = metasForDoc.length > 0 ? metasForDoc : priorMetas;
                    const evidenceImages = figureLabels.map((label, idx2) => {
                      const strictImageId = pickFigureImageIdStrictByLabel(label, metasPool);
                      const fallbackImageId = pickFigureImageId(
                        { figure_label: label, figure_id: label },
                        idx2,
                        metasPool,
                      );
                      const placeholderSrc = getEvidenceImageUrlPlaceholder(label);
                      const primaryImageSrc = strictImageId
                        ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(strictImageId)}`
                        : fallbackImageId
                          ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                          : placeholderSrc;
                      const secondaryImageSrc =
                        strictImageId && fallbackImageId && strictImageId !== fallbackImageId
                          ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                          : null;
                      return { label, primaryImageSrc, secondaryImageSrc, placeholderSrc };
                    });
                    return (
                      <div className="space-y-4 rounded border border-gray-200 p-4" key={`oa-map-${dIdx}-${mIdx}`}>
                        <div className="text-[15.5px] leading-[1.8] text-gray-900">
                          <strong className="mr-2 font-black">本案特征：</strong>
                          <span className="border-b border-gray-200 pb-0.5 font-bold">{toText(mapping.target_feature)}</span>
                        </div>

                        <div className="mb-4 mt-2 flex flex-wrap items-center gap-2">
                          <span className="mr-1 text-[13px] font-bold text-gray-500">对比文件溯源：</span>
                          {renderOutlinedTag(toText(mapping.prior_art_doc), true)}
                          {mapping.cited_paragraphs ? renderOutlinedTag(toText(mapping.cited_paragraphs)) : null}
                          {mapping.cited_figures ? renderOutlinedTag(toText(mapping.cited_figures)) : null}
                        </div>

                        {textSource && textSource !== "当前节点暂无输出。" && textSource !== "-" ? (
                          <div className="border-l-2 border-gray-300 pl-5">
                            <strong className="mb-2 block text-[14px] text-gray-800">对比文件文字溯源：</strong>
                            <p className="font-serif text-[14.5px] italic leading-[1.8] text-gray-700 text-justify">
                              {textSource}
                            </p>
                          </div>
                        ) : null}

                        {evidenceImages.length > 0 ? (
                          <div className="border-l-2 border-gray-200 pl-5">
                            <strong className="mb-3 block text-[14px] text-gray-800">对比文件图片溯源：</strong>
                            <div className={`grid gap-3 ${evidenceImages.length > 1 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1"}`}>
                              {evidenceImages.map((img, imgIdx) => (
                                <div className="rounded border border-gray-200 p-2" key={`oa-map-fig-${dIdx}-${mIdx}-${imgIdx}`}>
                                  <img
                                    alt={`${priorArtDoc} ${img.label}`}
                                    className="h-44 w-full object-contain"
                                    loading="lazy"
                                    onError={(e) => {
                                      const node = e.currentTarget;
                                      if (img.secondaryImageSrc && node.src !== img.secondaryImageSrc) {
                                        node.src = img.secondaryImageSrc;
                                        return;
                                      }
                                      if (node.src !== img.placeholderSrc) {
                                        node.src = img.placeholderSrc;
                                        return;
                                      }
                                      node.onerror = null;
                                    }}
                                    src={img.primaryImageSrc}
                                  />
                                  <div className="mt-2 border-b border-gray-300 pb-1 text-[12px] font-bold uppercase tracking-wide text-gray-700">
                                    {img.label}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <div className="mt-4 border-l-2 border-gray-300 pl-5">
                          <strong className="mb-2 block text-[14px] text-gray-800">审查意见：</strong>
                          <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">
                            {toText(mapping.examiner_logic)}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {defects.length === 0 ? <JsonFallback value={value} /> : null}
    </div>
  );
}

function MultimodalVerificationView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  const supportingItems = readArray(data?.supporting_items);
  if (!data || supportingItems.length === 0) {
    return <div className="p-8 text-center text-gray-500">加载定向图文核验数据中...</div>;
  }

  const extractFigureLabel = (textRaw: unknown): string => {
    const text = String(textRaw ?? "");
    if (!text) return "Fig.";
    const match = text.match(/附图\d+(-\d+)?/);
    return match ? match[0].replace("附图", "Fig.") : "Fig.";
  };

  const getWireframePlaceholder = (figLabelRaw: unknown): string => {
    const figLabel = String(figLabelRaw ?? "Fig.");
    return `https://dummyimage.com/600x400/ffffff/9ca3af.png&text=${encodeURIComponent(figLabel)}+Wireframe`;
  };

  const renderSmartIllustration = (textRaw: unknown) => {
    const text = String(textRaw ?? "");
    if (!text) return null;
    let imageTag: string | null = null;
    if (text.includes("滑动套") && text.includes("径向内移")) imageTag = "滑动套径向内移机理辅助图";
    else if (text.includes("密封圈") && text.includes("包裹式密封")) imageTag = "包裹式密封机理辅助图";
    else if (text.includes("腰型槽") || text.includes("导向块")) imageTag = "腰型槽/导向块拓扑辅助图";
    else if (text.includes("锥孔") && text.includes("钢珠")) imageTag = "锥孔-钢珠配合辅助图";
    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  const priorMetas = readArray(sessionData?.prior_art_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );

  const isValidConclusion = (() => {
    const c = String(data.overall_conclusion ?? "");
    if (!c) return false;
    return !c.includes("未提供") && !c.includes("补充");
  })();

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-6 text-3xl font-bold tracking-tight text-gray-900">对比文件核验</h2>

        <div className="mb-6 flex items-center gap-3">
          <span
            className={`rounded border px-2.5 py-0.5 text-[12.5px] font-bold uppercase tracking-wide ${
              data.examiner_conclusion_supported ? "border-emerald-300 text-emerald-700" : "border-rose-300 text-rose-700"
            }`}
          >
            审查员结论事实核查：{data.examiner_conclusion_supported ? "高度成立" : "事实驳回"}
          </span>
          <span className="rounded border border-gray-300 px-2.5 py-0.5 text-[12.5px] font-bold uppercase tracking-wide text-gray-600">
            置信度：{toText(data.confidence)}
          </span>
        </div>

        {isValidConclusion ? (
          <div className="max-w-4xl text-[15.5px] leading-[1.8] text-gray-800 text-justify">
            <strong className="text-gray-900">核验结论：</strong>
            {toText(data.overall_conclusion)}
          </div>
        ) : null}
      </div>

      <div className="space-y-24">
        <h3 className="mb-12 border-b border-gray-200 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          审查员认定事实核验
        </h3>

        <div className="space-y-20 pl-2">
          {supportingItems.map((item, idx) => {
            const s = readRecord(item) ?? {};
            const visualDisclosure = toText(s.prior_art_visual_disclosure);
            const figLabel = extractFigureLabel(visualDisclosure);
            const figureLabels = (() => {
              const m = String(visualDisclosure).match(/附图(\d+)(?:-(\d+))?/);
              if (!m) return [];
              const start = Number(m[1]);
              const end = m[2] ? Number(m[2]) : start;
              if (!Number.isFinite(start) || !Number.isFinite(end)) return [];
              const lo = Math.max(1, Math.min(start, end));
              const hi = Math.min(50, Math.max(start, end));
              const labels: string[] = [];
              for (let i = lo; i <= hi; i += 1) labels.push(`图${i}`);
              return labels;
            })();
            const candidateLabel = figureLabels[0] ?? figLabel.replace("Fig.", "图");
            const strictImageId = pickFigureImageIdStrictByLabel(candidateLabel, priorMetas);
            const fallbackImageId = pickFigureImageId(
              { figure_label: candidateLabel, figure_id: candidateLabel },
              0,
              priorMetas,
            );
            const placeholderSrc = getWireframePlaceholder(figLabel);
            const primaryImageSrc = strictImageId
              ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(strictImageId)}`
              : fallbackImageId
                ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                : placeholderSrc;
            const secondaryImageSrc =
              strictImageId && fallbackImageId && strictImageId !== fallbackImageId
                ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                : null;

            return (
              <div className="space-y-6" key={`targeted-verify-${idx}`}>
                <div className="text-[15.5px] leading-[1.8] text-gray-900">
                  <strong className="mr-2 border-b border-gray-300 pb-0.5 text-gray-900">本案被核验特征：</strong>
                  {toText(s.target_feature)}
                </div>

                <div className="mt-6 grid grid-cols-1 gap-12 lg:grid-cols-12">
                  <div className="space-y-3 lg:col-span-4">
                    <div className="border border-gray-200 bg-white p-2">
                      <img
                        alt={figLabel}
                        className="h-auto w-full object-cover opacity-80 mix-blend-multiply"
                        loading="lazy"
                        onError={(e) => {
                          const img = e.currentTarget;
                          if (secondaryImageSrc && img.src !== secondaryImageSrc) {
                            img.src = secondaryImageSrc;
                            return;
                          }
                          if (img.src !== placeholderSrc) {
                            img.src = placeholderSrc;
                            return;
                          }
                          img.onerror = null;
                        }}
                        src={primaryImageSrc}
                      />
                    </div>
                    <div className="flex items-baseline justify-between border-b border-gray-300 pb-1">
                      <span className="text-[13px] font-bold uppercase tracking-wide text-gray-900">附图：{figLabel}</span>
                    </div>
                  </div>

                  <div className="space-y-6 lg:col-span-8">
                    <div className="space-y-2 border-l-2 border-gray-300 pl-5">
                      <strong className="block text-[14.5px] text-gray-900">对比文件文字：</strong>
                      <p className="font-serif text-[14.5px] italic leading-[1.8] text-gray-700 text-justify">
                        {toText(s.prior_art_text_disclosure)}
                      </p>
                    </div>

                    <div className="space-y-2 pl-5">
                      <strong className="block text-[14.5px] text-gray-900">附图核验：</strong>
                      <p className="text-[14.5px] leading-[1.8] text-gray-800 text-justify">{visualDisclosure}</p>
                      {renderSmartIllustration(visualDisclosure)}
                    </div>

                    <div className="mt-4 border-t border-gray-100 pl-5 pt-4">
                      <strong className="mb-1 block text-[14.5px] text-gray-900">修改提示：</strong>
                      <p className="font-serif text-[14.5px] leading-[1.8] text-gray-600 text-justify">
                        {toText(s.amendment_avoidance_warning)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-24">
        <h3 className="mb-8 border-b border-gray-200 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          事实认定争议
        </h3>
        {readArray(data.disputable_items).length > 0 ? (
          <div className="pl-2 text-[14.5px] text-gray-700">...</div>
        ) : (
          <div className="pl-2 font-serif text-[14.5px] italic text-gray-400">
            经核验，暂未发现与审查员认定存在明显事实出入的争议点。
          </div>
        )}
      </div>
    </div>
  );
}

function GapAnalysisView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const claimAssessments = readArray(data.claim_assessments);
  const miningDirectives = readArray(data.mining_directives);
  const recommendedMerges = readArray(data.recommended_merges).map((x) => toText(x));
  const failedClaims = readArray(data.failed_claims).map((x) => toText(x));

  const inferredConfirmedPoints =
    readArray(data.confirmed_points).length > 0
      ? readArray(data.confirmed_points)
      : claimAssessments
          .map((item) => readRecord(item))
          .filter((item): item is Record<string, unknown> => !!item && String(item.status ?? "").toUpperCase() === "DEFEATED")
          .map((item) => `权利要求${toText(item.claim_number)}：${toText(item.reasoning)}`);

  const inferredGapTargets =
    readArray(data.gap_targets).length > 0
      ? readArray(data.gap_targets)
      : miningDirectives.map((item) => {
          const m = readRecord(item) ?? {};
          return toText(m.target_component_or_step ?? m.technical_gap_to_fill);
        });

  const renderSmartIllustration = (textRaw: unknown) => {
    const text = String(textRaw ?? "");
    if (!text) return null;

    let imageTag: string | null = null;
    if (text.includes("密封唇") && text.includes("流体腔")) {
      imageTag = "密封唇-流体腔微观耦合示意";
    } else if (text.includes("缓冲层") && text.includes("锯齿参数")) {
      imageTag = "缓冲层-锯齿参数关联示意";
    }

    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  const getStatusBadge = (statusRaw: unknown) => {
    const status = String(statusRaw ?? "").toUpperCase();
    let style = "border-gray-300 text-gray-600";
    let label = status || "UNKNOWN";

    if (status === "DEFEATED") {
      style = "border-rose-300 text-rose-700";
      label = "✗ 无效";
    } else if (status === "MERGE_CANDIDATE") {
      style = "border-emerald-300 text-emerald-700";
      label = "✓ 优质合并候选";
    } else if (status === "UNCERTAIN") {
      style = "border-amber-300 text-amber-700";
      label = "? 存疑/需论证";
    }
    return (
      <span className={`rounded border px-2.5 py-0.5 text-[12.5px] font-bold uppercase tracking-wide ${style}`}>
        {label}
      </span>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">修改方向确认</h2>

        <div className="max-w-4xl text-[15.5px] leading-[1.8] text-gray-800 text-justify">
          <strong className="text-gray-900">整体修改方向：</strong>
          {toText(data.overall_strategy_summary)}
        </div>
      </div>

      <div className="space-y-16">
        <h3 className="border-b border-gray-200 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          权利要求有效性分析
        </h3>

        <div className="mb-12 flex flex-wrap items-center gap-6 pl-2 text-[14.5px] font-mono">
          <div>
            <span className="text-gray-500">无效: </span>
            <strong className="text-gray-900">[{failedClaims.join(", ") || "-"}]</strong>
          </div>
          <div>
            <span className="text-gray-500">推荐合并: </span>
            <strong className="text-gray-900">[{recommendedMerges.join(", ") || "-"}]</strong>
          </div>
        </div>

        <div className="space-y-16 pl-2">
          {claimAssessments.length > 0 ? (
            claimAssessments.map((item, idx) => {
              const a = readRecord(item) ?? {};
              return (
                <div className="space-y-5" key={`assessment-${idx}`}>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                    <strong className="text-[16px] text-gray-900">权利要求 {toText(a.claim_number)}</strong>
                    {getStatusBadge(a.status)}
                  </div>

                  <div className="border-l-2 border-gray-300 pl-5">
                    <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">{toText(a.reasoning)}</p>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="text-sm text-gray-500">暂无权利要求评估明细。</p>
          )}
        </div>
      </div>

      <div className="mt-24 space-y-16">
        <h3 className="border-b border-gray-200 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          特征挖掘思路
        </h3>

        <div className="grid grid-cols-1 gap-16 pl-2 lg:grid-cols-2">
          <div>
            <strong className="mb-6 block border-b border-gray-100 pb-2 text-[15px] text-gray-900">
              既定事实妥协
            </strong>
            <ul className="list-disc space-y-2 pl-5 text-[14.5px] leading-[1.8] text-gray-700">
              {inferredConfirmedPoints.length > 0 ? (
                inferredConfirmedPoints.map((point, idx) => <li key={`confirmed-${idx}`}>{toText(point)}</li>)
              ) : (
                <li className="italic text-gray-500">暂无已定案事实。</li>
              )}
            </ul>
          </div>

          <div>
            <strong className="mb-6 block border-b border-gray-100 pb-2 text-[15px] text-gray-900">
              待挖掘特征
            </strong>
            <ul className="list-disc space-y-2 pl-5 text-[14.5px] font-bold leading-[1.8] text-gray-800">
              {inferredGapTargets.length > 0 ? (
                inferredGapTargets.map((target, idx) => <li key={`gap-${idx}`}>{toText(target)}</li>)
              ) : (
                <li className="italic font-normal text-gray-500">暂无备用特征。</li>
              )}
            </ul>
          </div>
        </div>

        <div className="pl-2 text-[15px] leading-[1.8] text-gray-800 text-justify">
          <strong className="text-gray-900">特征选择思路：</strong>
          {toText(data.rationale ?? data.overall_strategy_summary)}
        </div>

        <div className="pl-2 pt-10">
          <strong className="mb-8 block border-b border-gray-100 pb-2 text-[16px] uppercase tracking-widest text-gray-900">
            说明书特征挖掘
          </strong>

          <div className="space-y-16">
            {miningDirectives.length > 0 ? (
              miningDirectives.map((item, idx) => {
                const d = readRecord(item) ?? {};
                const targetText = toText(d.target_component_or_step);
                const gapText = toText(d.technical_gap_to_fill);
                return (
                  <div className="space-y-4" key={`directive-${idx}`}>
                    <div className="text-[15.5px] leading-[1.8] text-gray-900">
                      <strong className="text-gray-900">目标特征/步骤：</strong>
                      <span className="border-b border-gray-300 pb-0.5 font-bold">{targetText}</span>
                    </div>

                    <div className="text-[15px] leading-[1.8] text-gray-800">
                      <strong className="text-gray-900">填补技术空白：</strong>
                      {gapText}
                      {renderSmartIllustration(gapText)}
                    </div>

                    <div className="mt-4 border-l-2 border-gray-800 pl-5">
                      <strong className="mb-1 block text-[14.5px] text-gray-900">超范围提示：</strong>
                      <p className="font-serif text-[14.5px] italic leading-[1.8] text-gray-700 text-justify">
                        {toText(d.avoidance_warning)}
                      </p>
                    </div>
                  </div>
                );
              })
            ) : (
              <p className="text-sm text-gray-500">暂无说明书深度挖掘指令。</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FallbackFeatureMinerView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const candidates = readArray(data.candidates);
  if (candidates.length === 0) return <div className="p-8 text-center text-gray-500">加载特征挖掘数据中...</div>;

  const renderSmartIllustration = (textRaw: unknown) => {
    const text = String(textRaw ?? "");
    if (!text) return null;

    let imageTag: string | null = null;
    if (text.includes("密封唇") && text.includes("流体腔")) {
      imageTag = "密封唇-流体腔耦合示意";
    } else if (text.includes("缓冲层") && text.includes("预紧力")) {
      imageTag = "缓冲层-预紧力传递示意";
    }

    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <div className="mb-6 flex items-end gap-4">
          <h2 className="text-3xl font-bold tracking-tight text-gray-900">说明书特征挖掘</h2>
        </div>
      </div>

      <div className="space-y-24">
        {candidates.map((item, idx) => {
          const candidate = readRecord(item) ?? {};
          const featureNameRaw = String(candidate.feature_name ?? "").trim();
          if (!featureNameRaw) return null;

          const candidateId = String(candidate.candidate_id ?? idx + 1).replace(/_/g, " ");
          const directive = toText(candidate.addressed_directive);
          const referenceNumeral = toText(candidate.reference_numeral);
          const sourceLocation = toText(candidate.source_location);
          const quote = toText(candidate.verbatim_quote);
          const rationale = toText(candidate.gap_filling_rationale);

          return (
            <div key={`fallback-candidate-${idx}`}>
              <div className="mb-10 border-b border-gray-100 pb-4">
                <h3 className="text-2xl font-bold text-gray-900">
                  {candidateId}：{featureNameRaw}
                </h3>
              </div>

              <div className="space-y-8 pl-2">
                  <div className="text-[15.5px] leading-[1.8] text-gray-800">
                    <strong className="mr-1 text-gray-900">挖掘提示：</strong>
                    <span className="border-b border-gray-200 pb-0.5">{directive}</span>
                  </div>

                  <div>
                    <span className="rounded border border-gray-300 px-2.5 py-0.5 font-mono text-[12.5px] font-bold text-gray-600">
                      部件标号锚点：{referenceNumeral}
                    </span>
                  </div>

                  <div>
                    <strong className="mb-3 block text-[15.5px] text-gray-900">说明书原话摘抄：</strong>
                    <div className="space-y-4 border-l-2 border-gray-300 pl-5">
                      <p className="font-serif text-[15.5px] italic leading-[1.8] text-gray-700 text-justify">“{quote}”</p>
                      <div>
                        <span className="rounded border border-gray-300 px-2.5 py-0.5 font-mono text-[12.5px] font-bold text-gray-600">
                          溯源：说明书段落 {sourceLocation}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 text-[15.5px] leading-[1.8] text-gray-800 text-justify">
                    <strong className="mr-1 text-gray-900">合规与填补思路：</strong>
                    {rationale}
                    {renderSmartIllustration(rationale)}
                  </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PriorArtStressTesterView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const testedFeatures = readArray(data.tested_features);
  if (testedFeatures.length === 0) return <div className="p-8 text-center text-gray-500">加载压测数据中...</div>;

  const renderSmartIllustration = (textRaw: unknown) => {
    const text = String(textRaw ?? "");
    if (!text) return null;

    let imageTag: string | null = null;
    if (text.includes("包裹式密封") || text.includes("密封唇径向外张")) {
      imageTag = "包裹式密封与径向外张等效示意";
    } else if (text.includes("限位块") && text.includes("锥头端")) {
      imageTag = "限位块与锥头端接触关系示意";
    }

    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  const getVerdictBadge = (verdictRaw: unknown) => {
    const verdict = String(verdictRaw ?? "").toUpperCase();
    let style = "border-gray-300 text-gray-600";
    let label = verdict || "UNKNOWN";

    if (verdict === "ELIMINATED") {
      style = "border-red-300 text-red-700";
      label = "✗ 无效";
    } else if (verdict === "SURVIVED") {
      style = "border-emerald-300 text-emerald-700";
      label = "✓ 有效";
    }

    return (
      <span className={`rounded border px-3 py-0.5 text-[12.5px] font-bold uppercase tracking-widest ${style}`}>
        {label}
      </span>
    );
  };

  const survivedCandidateIds = readArray(data.survived_candidate_ids).map((x) => toText(x));

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">候选特征审查</h2>

        <div className="text-[15.5px] leading-[1.8] text-gray-800">
          <strong className="mr-2 font-black tracking-wide text-gray-900">全局候选特征有效性：</strong>
          <span className="font-mono">{toText(data.overall_survival_rate)}</span>
        </div>

        {survivedCandidateIds.length > 0 ? (
          <div className="mt-2 text-[15.5px] leading-[1.8] text-gray-800">
            <strong className="mr-2 text-emerald-700">幸存特征 ID：</strong>
            <span className="font-mono">{survivedCandidateIds.join(", ")}</span>
          </div>
        ) : null}
      </div>

      <div className="space-y-24">
        {testedFeatures.map((item, idx) => {
          const feature = readRecord(item) ?? {};
          const hitLocation = toText(feature.prior_art_hit_location);
          const candidateName = String(feature.candidate_id ?? "").replace(/_/g, " ");

          return (
            <div key={`stress-${idx}`}>
              <div className="mb-10 flex flex-col gap-4 border-b border-gray-100 pb-4 sm:flex-row sm:items-baseline">
                <h3 className="text-2xl font-bold text-gray-900">{candidateName || `候选特征 ${idx + 1}`}</h3>
                {getVerdictBadge(feature.test_verdict)}
              </div>

              <div className="space-y-8 pl-2">
                  <div className="text-[15.5px] leading-[1.8] text-gray-800">
                    <strong className="mr-1 text-gray-900">被测特征：</strong>
                    <span className="border-b border-gray-200 pb-0.5">{toText(feature.feature_name)}</span>
                  </div>

                  <div className="text-[15.5px] leading-[1.8] text-gray-800 text-justify">
                    <strong className="mr-1 text-gray-900">对比文件公开：</strong>
                    {hitLocation}
                  </div>

                  <div className="pt-2">
                    <strong className="mb-3 block text-[15.5px] text-gray-900">无效判定：</strong>
                    <div className="space-y-4 border-l-[3px] border-gray-900 pl-5">
                      <p className="font-serif text-[15.5px] italic leading-[1.8] text-gray-800 text-justify">
                        {toText(feature.red_team_reasoning)}
                      </p>
                    </div>
                    <div className="pl-5">{renderSmartIllustration(feature.red_team_reasoning)}</div>
                  </div>

                  <div className="mt-6 border-t border-gray-100 pt-4 text-[15px] leading-[1.8] text-gray-600">
                    <strong className="mr-1 text-gray-500">反驳基础：</strong>
                    <span className="font-serif italic">{toText(feature.rebuttal_foundation)}</span>
                  </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StrategyDecisionView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <div className="p-8 text-center text-gray-500">加载策略决策数据中...</div>;

  const amendmentPlan = readRecord(data.amendment_plan);
  const rebuttalPlan = readArray(data.rebuttal_plan);
  const sourceDependentClaims = readArray(amendmentPlan?.source_dependent_claims).map((x) => toText(x));

  const renderSmartIllustration = (textRaw: unknown) => {
    const text = String(textRaw ?? "");
    if (!text) return null;

    let imageTag: string | null = null;
    if (text.includes("圆锥形滑块") && text.includes("锥孔")) {
      imageTag = "圆锥形滑块-锥孔协同结构示意";
    } else if (text.includes("流体腔") && text.includes("缓冲层")) {
      imageTag = "流体腔-缓冲层协同响应示意";
    }

    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-12">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">答复策略</h2>

        <div className="border-l-[3px] border-gray-900 pl-5">
          <strong className="mb-3 block text-[15.5px] text-gray-900">全局答复策略：</strong>
          <p className="font-serif text-[15.5px] italic leading-[1.9] text-gray-800 text-justify">{toText(data.strategy_rationale)}</p>
        </div>
      </div>

      {amendmentPlan ? (
        <div className="mb-24 space-y-12">
          <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
            权利要求修改
          </h3>

          <div className="space-y-6 pl-2 text-[15.5px] leading-[1.8] text-gray-800">

            <div>
              <strong className="text-gray-900">目标独立权项：</strong>
              权利要求 {toText(amendmentPlan.target_independent_claim)}
            </div>

            <div>
              <strong className="text-gray-900">源自从属权项：</strong>[{sourceDependentClaims.join(", ")}]
            </div>

            <div>
              <strong className="text-gray-900">修改策略：</strong>
              {toText(amendmentPlan.amendment_guidance)}
            </div>
          </div>
        </div>
      ) : null}

      {rebuttalPlan.length > 0 ? (
        <div>
          <h3 className="mb-12 border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
            合并后创造性论述
          </h3>

          <div className="space-y-20 pl-2">
            {rebuttalPlan.map((item, idx) => {
              const rebuttal = readRecord(item) ?? {};
              const coreLogic = toText(rebuttal.core_argument_logic);
              return (
                <div className="space-y-8" key={`strategy-rebuttal-${idx}`}>
                  <div className="text-[16px] font-bold text-gray-900">目标: 修改后的权利要求 {toText(rebuttal.target_claim)}</div>

                  <div className="text-[15.5px] leading-[1.8] text-gray-800 text-justify">
                    <strong className="mb-2 block text-gray-900">创造性论述：</strong>
                    {coreLogic}
                    {renderSmartIllustration(coreLogic)}
                  </div>

                  <div className="mt-6 border-l-2 border-gray-300 pl-5">
                    <strong className="mb-2 block text-[14.5px] text-gray-900">非显而易见性论述：</strong>
                    <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">{toText(rebuttal.evidence_support)}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ClaimAmendmentView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <div className="p-8 text-center text-gray-500">加载修改定稿数据中...</div>;

  const claimMappings = readArray(data.claim_mappings);
  if (claimMappings.length === 0) return <div className="p-8 text-center text-gray-500">加载修改定稿数据中...</div>;

  const getAmendmentBadge = (typeRaw: unknown) => {
    const type = String(typeRaw ?? "").toUpperCase();
    let label = type || "UNKNOWN";
    let borderColor = "border-gray-300 text-gray-600";

    if (type === "MODIFIED_WITH_NEW_FEATURE") {
      label = "实质性重构";
      borderColor = "border-gray-900 text-gray-900 font-bold";
    } else if (type === "MERGED_INTO_INDEPENDENT") {
      label = "已并入/删除";
      borderColor = "border-gray-400 text-gray-500 border-dashed";
    } else if (type === "UNCHANGED") {
      label = "依序顺延";
    }

    return (
      <span className={`rounded border px-2.5 py-0.5 font-mono text-[12.5px] uppercase tracking-wide ${borderColor}`}>
        {label}
      </span>
    );
  };

  const finalClaimsText = String(data.final_claims_text ?? "");
  const finalClaimsArray = finalClaimsText ? finalClaimsText.split(/\r?\n/) : [];

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-12">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">权利要求修改</h2>

        {data.amendment_basis_statement ? (
          <div className="border-l-[3px] border-gray-900 py-1 pl-5">
            <strong className="mb-3 block text-[14.5px] font-bold uppercase tracking-widest text-gray-900">
              《专利法》第33条合规确认
            </strong>
            <p className="font-serif text-[15.5px] italic leading-[1.9] text-gray-800 text-justify">
              {toText(data.amendment_basis_statement)}
            </p>
          </div>
        ) : null}
      </div>

      <div className="mb-24 space-y-16">
        <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          修改过程
        </h3>

        <div className="space-y-16 pl-2">
          {claimMappings.map((item, idx) => {
            const mapping = readRecord(item) ?? {};
            const originalNo = toText(mapping.original_claim_number);
            const newNo = toText(mapping.new_claim_number);
            const amendedText = toText(mapping.amended_text);
            const guidance = toText(mapping.amendment_guidance);
            const amendmentType = String(mapping.amendment_type ?? "").toUpperCase();
            const isDeleted = newNo === "无";

            return (
              <div className="space-y-6" key={`claim-map-${idx}`}>
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-baseline gap-3">
                    <span className="text-[18px] font-bold text-gray-400">原 Claim {originalNo}</span>
                    <svg className="h-5 w-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path d="M17 8l4 4m0 0l-4 4m4-4H3" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                    </svg>
                    <span className={`text-[20px] font-black ${isDeleted ? "text-gray-300 line-through" : "text-gray-900"}`}>
                      新 Claim {newNo}
                    </span>
                  </div>
                  <div className="ml-2">{getAmendmentBadge(amendmentType)}</div>
                </div>

                <div className="space-y-5">
                  {guidance && guidance !== "无" ? (
                    <div className="text-[15px] leading-[1.8] text-gray-700">
                      <strong className="mr-2 text-gray-900">执行指引：</strong>
                      {guidance}
                    </div>
                  ) : null}

                  {!isDeleted && amendedText !== "无" ? (
                    <div className="mt-4 border-l-2 border-gray-300 pl-5">
                      <strong className="mb-2 block font-mono text-[14px] uppercase tracking-wider text-gray-500">修改后:</strong>
                      <p className="font-serif text-[15.5px] leading-[2] text-gray-900 text-justify">{amendedText}</p>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="pt-10">
        <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <h3 className="text-xl font-bold uppercase tracking-widest text-gray-900">修改后的完整权利要求</h3>
          <button className="rounded border border-gray-300 px-4 py-1.5 text-[13px] font-bold text-gray-600 transition-colors hover:border-gray-900 hover:text-gray-900">
            复制替换页全文
          </button>
        </div>

        <div className="border-y border-gray-300 py-12">
          <div className="space-y-6">
            {finalClaimsArray.map((claimText, idx) => (
              <p className="indent-8 font-serif text-[15.5px] leading-[2.4] text-gray-900 text-justify" key={`final-claim-${idx}`}>
                {claimText}
              </p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SpecUpdateView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data || !readArray(data.amendment_items)) return <div className="p-8 text-center text-gray-500">加载说明书勘误数据中...</div>;

  const amendmentItems = readArray(data.amendment_items);
  const applied = data.applied === true || data.requires_spec_update === true;
  const changes = readArray(data.changes);

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end">
          <h2 className="text-3xl font-bold tracking-tight text-gray-900">说明书修改</h2>
          <span
            className={`mb-1 rounded border px-3 py-1 text-[13px] font-bold uppercase tracking-widest ${
              applied ? "border-gray-900 text-gray-900" : "border-gray-400 text-gray-500"
            }`}
          >
            {applied ? "✓ 已全局应用" : "未应用"}
          </span>
        </div>

        <div className="max-w-4xl border-l-[3px] border-gray-900 py-1 pl-5">
          <strong className="mb-3 block text-[14.5px] font-bold uppercase tracking-widest text-gray-900">
            《专利法》第33条合规声明
          </strong>
          <p className="font-serif text-[15.5px] italic leading-[1.9] text-gray-800 text-justify">
            {toText(data.article_33_declaration)}
          </p>
        </div>
      </div>

      <div className="space-y-20">
        {amendmentItems.map((item, idx) => {
          const row = readRecord(item) ?? {};
          return (
            <div className="space-y-6" key={`spec-fine-${idx}`}>
              <div className="mb-6 flex items-center gap-4 border-b border-gray-100 pb-3">
                <strong className="text-[16px] tracking-wide text-gray-900">修改点</strong>
                <span className="rounded border border-gray-300 px-2.5 py-0.5 font-mono text-[13.5px] font-bold text-gray-700">
                  {toText(row.target_paragraph)}
                </span>
              </div>

              <div className="space-y-4 pl-2">
                <div className="text-[15px] leading-[1.8]">
                  <strong className="mr-3 font-mono text-gray-500">[-] 原始文本：</strong>
                  <span className="font-serif text-gray-400 line-through decoration-gray-300">{toText(row.original_text_snippet)}</span>
                </div>

                <div className="text-[15.5px] leading-[1.8]">
                  <strong className="mr-3 font-mono text-gray-900">[+] 勘误文本：</strong>
                  <span className="font-serif font-medium text-gray-900">{toText(row.amended_text_snippet)}</span>
                </div>
              </div>

              <div className="mt-6 ml-2 border-l-2 border-gray-300 pl-5">
                <strong className="mb-2 block text-[14.5px] text-gray-900">A33 修改依据：</strong>
                <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">{toText(row.amendment_reason)}</p>
              </div>
            </div>
          );
        })}
      </div>

      {changes.length > 0 ? (
        <div className="mt-24 border-t border-gray-200 pt-10">
          <strong className="mb-8 block text-[16px] uppercase tracking-widest text-gray-900">完整说明书修改</strong>

          <div className="space-y-4 pl-2 font-mono text-[13px] text-gray-600">
            {changes.map((change, idx) => (
              <div className="flex items-start gap-4" key={`spec-change-${idx}`}>
                <span className="mt-0.5 select-none text-gray-400">{`>`}</span>
                <span className="break-words text-justify leading-[1.8]">{toText(change)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MultimodalBaselineView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const claimsTree = readArray(data.claims_tree);
  if (claimsTree.length === 0) return <JsonFallback value={value} />;
  const appMetas = readArray(sessionData?.application_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );
  const getWireframePlaceholder = (figLabel: string): string => {
    const cleanLabel = figLabel ? figLabel.replace("图", "Fig.") : "Fig.";
    return `https://dummyimage.com/600x400/ffffff/9ca3af.png&text=${encodeURIComponent(cleanLabel)}+Wireframe`;
  };
  const renderSmartIllustration = (featureId: string) => {
    let imageTag: string | null = null;
    if (featureId === "F1.1") imageTag = "快插接头剖视结构辅助图";
    else if (featureId === "F1.4") imageTag = "半球面配合受力路径辅助图";
    else if (featureId === "F1.5") imageTag = "偏心锁止机构运动轨迹辅助图";
    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13.5px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-8">
        <h2 className="mb-4 text-3xl font-bold tracking-tight text-gray-900">申请文件分析</h2>
      </div>

      <div className="space-y-24">
        {claimsTree.map((claimItem, cIdx) => {
          const claim = readRecord(claimItem) ?? {};
          const atomicFeatures = readArray(claim.atomic_features);
          const dependency = readArray(claim.dependency).map((x) => toText(x));
          const isIndependent = claim.is_independent === true;

          return (
            <div key={`compare-baseline-claim-${cIdx}`}>
              <div className="mb-10 flex items-center gap-4 border-b border-gray-100 pb-4">
                <h3 className="text-2xl font-bold text-gray-900">权利要求 {toText(claim.claim_number)}</h3>
                <span className="rounded border border-gray-200 px-3 py-1 text-[13px] font-medium text-gray-700">
                  {isIndependent ? "独立权利要求" : `引用权利要求 ${dependency.join(", ")}`}
                </span>
              </div>

              <div className="space-y-16 pl-2">
                {atomicFeatures.map((featureItem, fIdx) => {
                  const feature = readRecord(featureItem) ?? {};
                  const entities = readArray(feature.entity_components);
                  const visualAnchor = readRecord(feature.visual_anchor) ?? {};
                  const figureLabels = readArray(visualAnchor.figure_labels).map((x) => toText(x)).filter((x) => !!x && x !== "当前节点暂无输出。");
                  const connection = toText(feature.connection_and_synergy);
                  const refNo = toText(visualAnchor.reference_numeral);
                  const visualMorphologyRaw = String(visualAnchor.visual_morphology ?? "");
                  const visualMorphology = visualMorphologyRaw || "未提取";
                  const featureId = toText(feature.feature_id);
                  const isExtractionIncomplete =
                    refNo === "无" || connection.includes("未提取") || visualMorphology.includes("未提取");

                  return (
                    <div className="space-y-6" key={`compare-baseline-feature-${cIdx}-${fIdx}`}>
                      <div className="text-[15.5px] leading-relaxed text-gray-800">
                        <strong className="text-gray-900">
                          特征 {featureId.split(".")[1] || featureId}：
                        </strong>
                        {toText(feature.verbatim_text)}
                      </div>

                      {entities.length > 0 && (
                        <div className="text-[14.5px] leading-relaxed text-gray-700">
                          <strong className="text-gray-900">提取特征：</strong>
                          {entities.map((entity) => toText(entity)).join("、")}
                        </div>
                      )}

                      {!isExtractionIncomplete ? (
                        <div className="mt-8 grid grid-cols-1 gap-12 lg:grid-cols-12">
                          <div className="space-y-6 lg:col-span-4">
                            {figureLabels.length > 0 ? (
                              figureLabels.map((figText, figIdx) => {
                                const strictImageId = pickFigureImageIdStrictByLabel(figText, appMetas);
                                const fallbackImageId = pickFigureImageId(
                                  { figure_label: figText, figure_id: figText },
                                  figIdx,
                                  appMetas,
                                );
                                const placeholderSrc = getWireframePlaceholder(figText);
                                const primaryImageSrc = strictImageId
                                  ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(strictImageId)}`
                                  : fallbackImageId
                                    ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                                    : placeholderSrc;
                                const secondaryImageSrc =
                                  strictImageId && fallbackImageId && strictImageId !== fallbackImageId
                                    ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                                    : null;
                                return (
                                  <div className="space-y-2" key={`compare-anchor-image-${cIdx}-${fIdx}-${figIdx}`}>
                                    <div className="border border-gray-200 p-2">
                                      <img
                                        alt={figText}
                                        className="h-auto w-full object-cover opacity-80 mix-blend-multiply"
                                        loading="lazy"
                                        onError={(e) => {
                                          const img = e.currentTarget;
                                          if (secondaryImageSrc && img.src !== secondaryImageSrc) {
                                            img.src = secondaryImageSrc;
                                            return;
                                          }
                                          if (img.src !== placeholderSrc) {
                                            img.src = placeholderSrc;
                                            return;
                                          }
                                          img.onerror = null;
                                        }}
                                        src={primaryImageSrc}
                                      />
                                    </div>
                                    <div className="border-b border-gray-300 pb-1 text-[13px] font-bold uppercase tracking-wide text-gray-900">
                                      {figText}
                                    </div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="border-b border-gray-300 pb-1 text-[13px] font-bold uppercase tracking-wide text-gray-900">
                                {refNo}
                              </div>
                            )}
                          </div>

                          <div className="space-y-8 lg:col-span-8">
                            <div className="border-l-2 border-gray-300 pl-5">
                              <strong className="mb-2 block text-[15px] text-gray-900">连接关系：</strong>
                              <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">
                                {connection}
                              </p>
                              {renderSmartIllustration(featureId)}
                            </div>

                            <div className="pl-5">
                              <strong className="mb-2 block text-[15px] text-gray-900">视觉特征：</strong>
                              <p className="text-[15px] leading-[1.8] text-gray-700 text-justify">
                                {visualMorphology}
                              </p>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-6 text-[14px] italic text-gray-400">
                          注：未发现明确的视觉形态描述或协同连接关系，需人工复核。
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

    </div>
  );
}

function PriorArtAnatomyView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const profiles = readArray(data.prior_art_profiles);
  if (profiles.length === 0) return <JsonFallback value={value} />;
  const getWireframePlaceholder = (figLabel: string): string => {
    const cleanLabel = figLabel ? figLabel.replace("图", "Fig.") : "Fig.";
    return `https://dummyimage.com/600x400/ffffff/9ca3af.png&text=${encodeURIComponent(cleanLabel)}+Wireframe`;
  };
  const renderSmartIllustration = (text: string) => {
    if (!text) return null;
    let imageTag: string | null = null;
    if (text.includes("锥面接触")) imageTag = "锥面接触导向结构辅助图";
    else if (text.includes("滑动配合")) imageTag = "滑动配合行程关系辅助图";
    else if (text.includes("O型密封圈") && text.includes("径向密封")) imageTag = "O型密封圈径向密封辅助图";
    if (!imageTag) return null;
    return (
      <div className="mt-3 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  const priorMetas = readArray(sessionData?.prior_art_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-8">
        <div className="mb-5 flex items-end gap-4">
          <h2 className="text-3xl font-bold tracking-tight text-gray-900">对比文件分析</h2>
          <span className="mb-1 rounded border border-gray-200 px-3 py-1 text-[13px] font-medium uppercase tracking-widest text-gray-700">
            Target: {toText(data.comparison_goal)}
          </span>
        </div>
        <div className="max-w-4xl text-[15.5px] leading-relaxed text-gray-800">
          <strong className="text-gray-900">全局技术概述：</strong>
          {toText(data.overall_summary)}
        </div>
      </div>

      <div className="space-y-24">
        {profiles.map((profileItem, pIdx) => {
          const profile = readRecord(profileItem) ?? {};
          const componentIndex = readArray(profile.component_index);
          const figureLibrary = readArray(profile.figure_library);
          const readingAudit = readRecord(profile.reading_audit);
          const docId = toText(profile.prior_art_id);

          const metasForDoc = priorMetas.filter((m) => {
            const hint = String(m.caption_hint ?? "");
            return hint.includes(docId) || hint.toUpperCase().includes(docId.toUpperCase());
          });
          const metas = metasForDoc.length > 0 ? metasForDoc : priorMetas;

          return (
            <div key={`prior-profile-${pIdx}`}>
              <div className="mb-12 border-b border-gray-100 pb-6">
                <h3 className="mb-4 text-2xl font-bold text-gray-900">对比文件 {docId}</h3>
                <div className="text-[15.5px] leading-relaxed text-gray-800">
                  <strong className="text-gray-900">核心解决问题：</strong>
                  {toText(profile.core_technical_problem_solved)}
                </div>
              </div>

              <div className="mb-16">
                <h4 className="mb-8 text-lg font-bold tracking-wide text-gray-900">
                  技术特征集合
                </h4>
                <div className="space-y-10 pl-2">
                  {componentIndex.map((compItem, cIdx) => {
                    const comp = readRecord(compItem) ?? {};
                    const refRaw = String(comp.reference_numeral ?? "无");
                    return (
                      <div className="space-y-3 rounded border border-gray-200 p-4" key={`prior-comp-${pIdx}-${cIdx}`}>
                        <div className="mb-2 flex items-center gap-3">
                          <span className="text-[16px] font-bold text-gray-900">{toText(comp.component_name)}</span>
                          <span className="rounded border border-gray-200 px-2 py-0.5 font-mono text-[12px] font-bold text-gray-600">
                            {refRaw}
                          </span>
                        </div>
                        <div className="text-[14.5px] leading-relaxed text-gray-700">
                          <strong className="text-gray-900">视觉形态：</strong>
                          {toText(comp.visual_appearance)}
                        </div>
                        <div className="text-[14.5px] leading-relaxed text-gray-700">
                          <strong className="text-gray-900">结构机制：</strong>
                          {toText(comp.structural_connections_and_mechanisms)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div>
                <h4 className="mb-10 text-lg font-bold tracking-wide text-gray-900">
                  附图技术特征结构
                </h4>
                <div className="space-y-20">
                  {figureLibrary.map((figItem, fIdx) => {
                    const fig = readRecord(figItem) ?? {};
                    const figLabel = toText(fig.figure_label);
                    const strictImageId = pickFigureImageIdStrictByLabel(figLabel, metas);
                    const fallbackImageId = pickFigureImageId({ figure_label: figLabel, figure_id: figLabel }, fIdx, metas);
                    const placeholderSrc = getWireframePlaceholder(figLabel);
                    const primaryImageSrc = strictImageId
                      ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(strictImageId)}`
                      : fallbackImageId
                        ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                        : placeholderSrc;
                    const secondaryImageSrc =
                      strictImageId && fallbackImageId && strictImageId !== fallbackImageId
                        ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                        : null;
                    const observed = readArray(fig.observed_components);
                    const connections = readArray(fig.visual_connections);

                    return (
                      <div className="grid grid-cols-1 gap-12 lg:grid-cols-12" key={`prior-fig-${pIdx}-${fIdx}`}>
                        <div className="space-y-5 lg:col-span-4">
                          <div className="space-y-2">
                            <div className="border border-gray-200 bg-white p-2">
                              <img
                                alt={`${docId} ${figLabel}`}
                                className="h-auto w-full object-cover opacity-80 mix-blend-multiply"
                                loading="lazy"
                                onError={(e) => {
                                  const img = e.currentTarget;
                                  if (secondaryImageSrc && img.src !== secondaryImageSrc) {
                                    img.src = secondaryImageSrc;
                                    return;
                                  }
                                  if (img.src !== placeholderSrc) {
                                    img.src = placeholderSrc;
                                    return;
                                  }
                                  img.onerror = null;
                                }}
                                src={primaryImageSrc}
                              />
                            </div>
                            <div className="flex items-baseline justify-between border-b border-gray-300 pb-1">
                              <span className="text-[13px] font-bold uppercase tracking-wide text-gray-900">
                                {figLabel}
                              </span>
                            </div>
                          </div>

                          <div className="pt-2">
                            <strong className="mb-2 block text-[13px] text-gray-900">观测标号：</strong>
                            <div className="flex flex-wrap gap-2">
                              {observed.map((obs, oIdx) => (
                                <span
                                  className="rounded border border-gray-200 px-1.5 py-0.5 font-mono text-[12px] text-gray-600"
                                  key={`prior-obs-${pIdx}-${fIdx}-${oIdx}`}
                                >
                                  #{toText(obs)}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div className="space-y-8 border-gray-200 pl-0 lg:col-span-8 lg:border-l-2 lg:pl-6">
                          {connections.map((connItem, cIdx) => {
                            const conn = readRecord(connItem) ?? {};
                            const relationText = toText(conn.kinematic_relationship);
                            return (
                              <div className="space-y-2" key={`prior-conn-${pIdx}-${fIdx}-${cIdx}`}>
                                <div className="mb-2 flex items-center gap-3">
                                  <strong className="text-[14.5px] text-gray-900">{toText(conn.source_component)}</strong>
                                  <svg className="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path d="M17 8l4 4m0 0l-4 4m4-4H3" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
                                  </svg>
                                  <strong className="text-[14.5px] text-gray-900">{toText(conn.target_component)}</strong>
                                </div>
                                <p className="pl-2 font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">
                                  {relationText}
                                </p>
                                <div className="pl-2">{renderSmartIllustration(relationText)}</div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>
          );
        })}
      </div>
    </div>
  );
}

function FeatureMatrixCollisionView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const reports = readArray(data.prior_art_targeted_report);
  if (reports.length === 0) return <JsonFallback value={value} />;

  const renderSmartIllustration = (text: string) => {
    if (!text || text.includes("未发现") || text.includes("未提供")) return null;
    let hint: string | null = null;
    if (text.includes("锥面")) hint = "锥面结构图解参考";
    else if (text.includes("滑动配合")) hint = "滑动配合图解参考";
    else if (text.includes("O型密封圈")) hint = "O型密封圈图解参考";
    else if (text.includes("螺纹连接")) hint = "螺纹连接图解参考";
    if (!hint) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13.5px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{hint}</span>
      </div>
    );
  };

  const getSafetyBadge = (statusRaw: unknown) => {
    const status = String(statusRaw ?? "").toUpperCase();
    if (status === "AT_RISK") {
      return (
        <span className="rounded border border-red-200 px-3 py-1 text-[13px] font-bold tracking-wide text-red-700">
          ⚠️ 存在风险
        </span>
      );
    }
    return (
      <span className="rounded border border-green-200 px-3 py-1 text-[13px] font-bold tracking-wide text-green-700">
        ✓ 相对安全
      </span>
    );
  };

  const getDisclosureStatusText = (statusRaw: unknown) => {
    const status = String(statusRaw ?? "").toUpperCase();
    if (status === "EXPLICIT") return "明确文字公开";
    if (status === "IMPLICIT_VISUAL") return "图示隐含公开";
    if (status === "NOT_DISCLOSED") return "未公开";
    return status;
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-8">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">特征比对</h2>
        <div className="max-w-4xl text-[15.5px] leading-[1.8] text-gray-800 text-justify">
          <strong className="text-gray-900">全局比对结果：</strong>
          {toText(data.global_conclusion)}
        </div>
      </div>

      <div className="space-y-24">
        {reports.map((reportItem, rIdx) => {
          const report = readRecord(reportItem) ?? {};
          const collisions = readArray(report.feature_collisions);
          return (
            <div key={`matrix-report-${rIdx}`}>
              <div className="mb-10 flex flex-col gap-4 border-b border-gray-100 pb-4 sm:flex-row sm:items-center">
                <h3 className="text-2xl font-bold text-gray-900">权利要求 {toText(report.claim_number)}</h3>
                {getSafetyBadge(report.claim_safety_status)}
              </div>

              <div className="space-y-16 pl-2">
                {collisions.map((collisionItem, cIdx) => {
                  const collision = readRecord(collisionItem) ?? {};
                  const disclosureStatus = String(collision.disclosure_status ?? "").toUpperCase();
                  const isNotDisclosed = disclosureStatus === "NOT_DISCLOSED";
                  const textEvidence = toText(collision.text_evidence);
                  const visualEvidence = toText(collision.visual_evidence);
                  const hasRealEvidence =
                    !isNotDisclosed &&
                    !!textEvidence &&
                    !textEvidence.includes("未发现") &&
                    !textEvidence.includes("未提供");
                  return (
                    <div className="space-y-6" key={`matrix-collision-${rIdx}-${cIdx}`}>
                      <div className="mb-6 flex flex-wrap items-center gap-3">
                        <span className="rounded border border-gray-300 px-2.5 py-1 text-[13.5px] font-bold text-gray-900">
                          本案 {toText(collision.feature_id)}
                        </span>
                        <span className="select-none font-serif text-[14px] italic text-gray-400">vs</span>
                        <span className="rounded border border-gray-300 px-2.5 py-1 text-[13.5px] font-bold text-gray-900">
                          对比 {toText(collision.prior_art_id)}
                        </span>
                        <span className="ml-2 rounded border border-gray-200 px-2.5 py-1 text-[13px] font-medium text-gray-600">
                          公开状态：{getDisclosureStatusText(collision.disclosure_status)}
                        </span>
                      </div>

                      <div className="space-y-2 text-[15px] leading-relaxed text-gray-800">
                        <div>
                          <strong className="text-gray-900">部件比对：</strong>
                          {toText(collision.component_match_status)}
                        </div>
                        <div>
                          <strong className="text-gray-900">关系比对：</strong>
                          {toText(collision.relationship_match_status)}
                        </div>
                      </div>

                      <div className="mt-8 space-y-8 border-l-2 border-gray-300 pl-5">
                        {hasRealEvidence ? (
                          <div className="space-y-4">
                            <strong className="mb-2 block text-[15px] text-gray-900">客观事实：</strong>
                            <div className="space-y-3 text-[14.5px] leading-[1.8] text-gray-700 text-justify">
                              <div>
                                <strong className="text-gray-800">文字证据：</strong>
                                {textEvidence}
                              </div>
                              <div>
                                <strong className="text-gray-800">视觉比对：</strong>
                                {visualEvidence}
                              </div>
                            </div>
                            {renderSmartIllustration(visualEvidence)}
                          </div>
                        ) : null}

                        <div>
                          <strong className="mb-2 block text-[15px] text-gray-900">比对结果：</strong>
                          <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">
                            {toText(collision.collision_reasoning)}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RiskAssessmentView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const claimAssessments = readArray(data.claim_assessments);
  if (claimAssessments.length === 0) return <JsonFallback value={value} />;

  const renderSmartTopologyImage = (text: string) => {
    if (!text) return null;
    let imageTag: string | null = null;
    if (text.includes("内凹半球面") && text.includes("外凸半球面")) imageTag = "内凹/外凸半球面配合拓扑辅助图";
    else if (text.includes("三斜面等斜度")) imageTag = "三斜面等斜度锁止拓扑辅助图";
    else if (text.includes("倒角") && text.includes("半包围空间")) imageTag = "倒角半包围空间拓扑辅助图";
    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  const getRiskBadge = (type: "novelty" | "inventiveness", levelRaw: unknown) => {
    const level = String(levelRaw ?? "").toUpperCase();
    let colorClass = "border-gray-300 text-gray-600";
    if (level === "SAFE") colorClass = "border-emerald-300 text-emerald-700";
    else if (level === "LOW") colorClass = "border-amber-300 text-amber-700";
    else if (level === "MEDIUM") colorClass = "border-orange-300 text-orange-700";
    else if (level === "HIGH") colorClass = "border-rose-300 text-rose-700";
    const label = type === "novelty" ? `新颖性：${level || "UNKNOWN"}` : `创造性：${level || "UNKNOWN"}`;
    return (
      <span className={`rounded border px-2.5 py-0.5 text-[12.5px] font-bold uppercase tracking-wide ${colorClass}`}>
        {label}
      </span>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">风险评估</h2>
        <div className="max-w-4xl space-y-6 text-[15.5px] leading-[1.8] text-gray-800">
          <div>
            <strong className="text-gray-900">全局风险评估结果：</strong>
            {toText(data.global_risk_summary)}
          </div>
          <div>
            <strong className="text-gray-900">修改策略：</strong>
            {toText(data.strategic_amendment_direction)}
          </div>
        </div>
      </div>

      <div className="space-y-24">
        {claimAssessments.map((assessmentItem, idx) => {
          const assessment = readRecord(assessmentItem) ?? {};
          const topologyText = toText(assessment.topology_difference_analysis);
          const robustFeatures = readArray(assessment.robust_distinguishing_features);
          return (
            <div key={`risk-assessment-${idx}`}>
              <div className="mb-8 flex flex-col gap-4 border-b border-gray-100 pb-3 sm:flex-row sm:items-center">
                <h3 className="text-2xl font-bold text-gray-900">权利要求 {toText(assessment.claim_number)}</h3>
                <div className="flex items-center gap-2">
                  {getRiskBadge("novelty", assessment.novelty_risk)}
                  {getRiskBadge("inventiveness", assessment.inventiveness_risk)}
                </div>
              </div>

              <div className="space-y-8 pl-2">
                <div className="text-[15px] leading-[1.8] text-gray-800">
                  <strong className="text-gray-900">结构差异分析：</strong>
                  {topologyText}
                  {renderSmartTopologyImage(topologyText)}
                </div>

                <div className="text-[15px] leading-[1.8] text-gray-800">
                  <strong className="text-gray-900">修改策略：</strong>
                  {toText(assessment.breakthrough_point)}
                </div>

                <div className="mt-10 border-l-2 border-gray-300 pl-5 pt-2">
                  <strong className="mb-4 block text-[15px] text-gray-900">区别特征：</strong>
                  {robustFeatures.length > 0 ? (
                    <ul className="list-decimal space-y-3 pl-5 font-serif text-[15px] italic leading-[1.8] text-gray-700">
                      {robustFeatures.map((feature, fIdx) => (
                        <li className="pl-1" key={`robust-${idx}-${fIdx}`}>
                          {toText(feature)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-[14.5px] italic text-gray-400">该权项未提取到有效的坚固区别特征。</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AmendmentSuggestionView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const amendments = readArray(data.concrete_amendments);
  if (amendments.length === 0) return <JsonFallback value={value} />;

  const renderSmartIllustration = (text: string) => {
    if (!text) return null;
    let imageTag: string | null = null;
    if (text.includes("内凹半球面") && text.includes("外凸半球面")) imageTag = "内凹/外凸半球面修改点辅助图";
    else if (text.includes("倒角") && text.includes("半包围空间")) imageTag = "倒角半包围空间修改点辅助图";
    else if (text.includes("三斜面等斜度")) imageTag = "三斜面等斜度锁止修改点辅助图";
    if (!imageTag) return null;
    return (
      <div className="mt-4 flex items-start gap-2 font-mono text-[13px] text-gray-500">
        <span className="select-none">↳</span>
        <span className="border-b border-gray-200 pb-0.5">{imageTag}</span>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-10">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">修改建议</h2>
        <div className="max-w-4xl text-[15.5px] leading-[1.8] text-gray-800 text-justify">
          <strong className="text-gray-900">全局修改建议：</strong>
          {toText(data.overall_rescue_strategy)}
        </div>
      </div>

      <div className="space-y-24">
        {amendments.map((item, idx) => {
          const amendment = readRecord(item) ?? {};
          const amendmentTypeText = String(amendment.amendment_type ?? "").replace(/_/g, " ");
          const targetClaim = toText(amendment.target_claim_number);
          const synergyText = toText(amendment.synergy_and_mechanism_focus);
          return (
            <div key={`amendment-${idx}`}>
              <div className="mb-8 flex flex-col gap-4 border-b border-gray-100 pb-3 sm:flex-row sm:items-center">
                <h3 className="text-2xl font-bold text-gray-900">针对权利要求 {targetClaim} 的修改方案</h3>
              </div>

              <div className="space-y-8 pl-2">
                <div className="text-[15.5px] leading-[1.8] text-gray-800">
                  <strong className="text-gray-900">引入目标特征：</strong>
                  <span className="border-b border-gray-300 pb-0.5 font-bold">{toText(amendment.source_feature_name)}</span>
                </div>

                <div className="border-l-2 border-gray-300 pl-5">
                  <strong className="mb-2 block text-[14.5px] text-gray-900">说明书原文溯源：</strong>
                  <p className="font-serif text-[14.5px] italic leading-[1.8] text-gray-700 text-justify">
                    {toText(amendment.source_location)}
                  </p>
                </div>

                <div className="text-[15px] leading-[1.8] text-gray-800">
                  <strong className="text-gray-900">引入文本：</strong>
                  <span className="rounded-sm bg-gray-50 px-2 py-0.5 font-serif">{toText(amendment.verbatim_addition)}</span>
                </div>

                <div className="grid grid-cols-1 gap-12 pt-4 lg:grid-cols-2">
                  <div className="text-[15px] leading-[1.8] text-gray-800">
                    <strong className="mb-2 block text-gray-900">作用机理：</strong>
                    <p className="text-justify">{synergyText}</p>
                    {renderSmartIllustration(synergyText)}
                  </div>

                  <div className="text-[15px] leading-[1.8] text-gray-800">
                    <strong className="mb-2 block text-gray-900">预期效果：</strong>
                    <p className="text-justify">{toText(amendment.expected_overcoming_effect)}</p>
                  </div>
                </div>

                <div className="mt-12 border-t border-gray-200 pt-8">
                  <strong className="mb-6 block text-[16px] uppercase tracking-wider text-gray-900">
                    修改后权利要求 {targetClaim} 
                  </strong>
                  <div className="border-y border-gray-200 py-8 font-serif text-[15.5px] leading-[2.2] text-gray-900 text-justify">
                    {toText(amendment.draft_amended_claim_text)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {data.article_33_compliance_statement ? (
        <div className="mt-24 border-t-[3px] border-gray-900 pt-10">
          <strong className="mb-4 block text-[14px] font-black uppercase tracking-widest text-gray-900">
            《专利法》第33条合规声明
          </strong>
          <p className="font-serif text-[14.5px] leading-[1.8] text-gray-700 text-justify">
            {toText(data.article_33_compliance_statement)}
          </p>
        </div>
      ) : null}

    </div>
  );
}

function FinalComplianceReviewView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <div className="p-8 text-center text-gray-500">加载终审审计数据中...</div>;

  const getSeverityBadge = (severityRaw: unknown) => {
    const severity = String(severityRaw ?? "").toUpperCase();
    let style = "border-gray-300 text-gray-500";
    if (severity === "FATAL") style = "border-red-600 text-red-700 font-black";
    else if (severity === "WARNING") style = "border-amber-500 text-amber-700";
    return <span className={`rounded border px-2.5 py-0.5 text-[12px] uppercase tracking-widest ${style}`}>{severity || "UNKNOWN"}</span>;
  };

  const supportBasisAudit = readArray(data.support_basis_audit);
  const mergedLogicAudit = [...readArray(data.logic_consistency_audit), ...readArray(data.harmful_admission_audit)];

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-12">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">逻辑审查</h2>

        <div className="border-l-[3px] border-gray-900 pl-5">
          <strong className="mb-3 block text-[15px] font-bold uppercase tracking-widest text-gray-900">审查风险综述</strong>
          <p className="font-serif text-[15.5px] italic leading-[1.9] text-red-800 text-justify">{toText(data.final_strategy_summary)}</p>
        </div>
      </div>

      <div className="space-y-24">
        <div className="space-y-16">
          <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
            法律支持依据审查
          </h3>
          <div className="space-y-20 pl-2">
            {supportBasisAudit.map((item, idx) => {
              const row = readRecord(item) ?? {};
              return (
                <div className="space-y-8" key={`support-audit-${idx}`}>
                  <div className="flex items-center gap-4">
                    {getSeverityBadge(row.severity)}
                    <span className="font-mono text-[14.5px] font-bold uppercase tracking-wider text-gray-500">
                      Category: {toText(row.risk_category)}
                    </span>
                  </div>

                  <div className="space-y-6">
                    <div className="text-[15.5px] leading-[1.8] text-gray-800">
                      <strong className="mb-2 block text-gray-900">问题文本：</strong>
                      <span className="rounded-sm bg-red-50 px-2 py-0.5 font-serif text-red-900">{toText(row.problematic_text)}</span>
                    </div>

                    <div className="border-l-2 border-gray-300 pl-5">
                      <strong className="mb-2 block text-[14.5px] text-gray-900">核验结果：</strong>
                      <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">{toText(row.audit_reasoning)}</p>
                    </div>

                    <div className="text-[15.5px] leading-[1.8] text-gray-800">
                      <strong className="mb-2 block text-gray-900">整改修改方案建议：</strong>
                      <p className="border-l-2 border-emerald-500 pl-2 font-medium text-emerald-900">{toText(row.suggested_remedy)}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-16 pt-10">
          <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
            逻辑一致性审查
          </h3>
          <div className="space-y-20 pl-2">
            {mergedLogicAudit.map((item, idx) => {
              const row = readRecord(item) ?? {};
              return (
                <div className="space-y-8" key={`logic-audit-${idx}`}>
                  <div className="flex items-center gap-4">
                    {getSeverityBadge(row.severity)}
                    <span className="font-mono text-[14.5px] font-bold uppercase tracking-wider text-gray-600">
                      {toText(row.risk_category)}
                    </span>
                  </div>

                  <div className="space-y-6">
                    <div className="text-[15.5px] leading-[1.8] text-gray-800">
                      <strong className="mb-2 block text-gray-900">存在风险表述：</strong>
                      <span className="font-serif italic text-gray-600">“{toText(row.problematic_text)}”</span>
                    </div>

                    <div className="border-l-2 border-gray-300 pl-5">
                      <strong className="mb-2 block text-[14.5px] text-gray-900">核验结果：</strong>
                      <p className="font-serif text-[15px] leading-[1.8] text-gray-700 text-justify">{toText(row.audit_reasoning)}</p>
                    </div>

                    <div className="text-[15.5px] leading-[1.8] text-gray-800">
                      <strong className="mb-2 block text-gray-900">整体修改方向建议：</strong>
                      <p className="font-bold text-gray-900">{toText(row.suggested_remedy)}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

    </div>
  );
}

function DraftClaimsView({ value }: { value: unknown }) {
  const claimSet = readRecord(value);
  const claims = readArray(claimSet?.claims);
  if (!claimSet || claims.length === 0) return <JsonFallback value={value} />;

  const toClaimText = (rawClaim: unknown, fallbackNumber: number) => {
    const claim = readRecord(rawClaim) ?? {};
    const claimNumber = toText(claim.claim_number ?? fallbackNumber).trim();
    const fullText = toText(claim.full_text).trim();
    if (fullText) return fullText;

    const preamble = toText(claim.preamble).trim();
    const transition = toText(claim.transition).trim();
    const elements = readArray(claim.elements)
      .map((element) => toText(element).trim())
      .filter(Boolean);

    const head = [preamble, transition].filter(Boolean).join("，");
    const tail = elements.join("；");
    const body = [head, tail].filter(Boolean).join("，");
    return body ? `权利要求${claimNumber}：${body}` : `权利要求${claimNumber}。`;
  };

  const fullClaimsText = claims.map((claim, idx) => toClaimText(claim, idx + 1));

  return (
    <div className="mx-auto w-full max-w-5xl space-y-12 pb-16">
      <div className="mt-4 flex items-end justify-between border-b border-gray-200 pb-6">
        <div>
          <h3 className="text-3xl font-bold text-gray-900">权利要求书草案</h3>
        </div>
        <div className="mb-1 text-sm text-gray-500">
          共生成 <span className="font-bold text-gray-800">{claims.length}</span> 项权利要求
        </div>
      </div>

      <div className="space-y-10">
        {claims.map((item, idx) => {
          const claim = readRecord(item) ?? {};
          const number = claim.claim_number ?? idx + 1;
          const claimType = String(claim.claim_type ?? "");
          const dependsOn = readArray(claim.depends_on).map((d) => toText(d));
          const elements = readArray(claim.elements);
          return (
            <article className="border-b border-gray-100 pb-10 last:border-0 last:pb-0" key={`draft-claim-${idx}`}>
              <div className="mb-5 flex items-center gap-3">
                <span className="text-xl font-bold text-gray-900">{toText(number)}.</span>
                {claimType === "independent" ? (
                  <span className="rounded bg-gray-800 px-3 py-1 text-xs font-bold text-white">独立权利要求</span>
                ) : (
                  <span className="rounded border border-gray-300 bg-white px-3 py-1 text-xs font-semibold text-gray-600">
                    从属权利要求{dependsOn.length > 0 ? `（引用权 ${dependsOn.join(", ")}）` : ""}
                  </span>
                )}
              </div>

              <div className="text-[15px] leading-relaxed text-gray-800">
                <div className="mb-3 font-medium">
                  {toText(claim.preamble)}
                  {claim.transition ? `，${toText(claim.transition)}` : ""}
                </div>

                {elements.length > 0 ? (
                  <ol className="ml-6 list-outside list-decimal space-y-4">
                    {elements.map((element, eIdx) => (
                      <li className="pl-2 text-justify text-gray-700" key={`el-${idx}-${eIdx}`}>{toText(element)}</li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-gray-700">{toText(claim.full_text)}</p>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <section className="space-y-4 border-t border-gray-200 pt-8">
        <h4 className="text-xl font-bold text-gray-900">完整权利要求</h4>
        <ol className="space-y-4 border-y border-gray-200 py-6">
          {fullClaimsText.map((text, idx) => (
            <li className="flex items-start gap-3" key={`full-claim-text-${idx}`}>
              <span className="min-w-8 text-right text-[15.5px] font-bold leading-[2] text-gray-900">{idx + 1}.</span>
              <p className="text-[15.5px] leading-[2] text-gray-900 font-serif text-justify">{text}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function ClaimsConfirmationReadonlyView({ value }: { value: unknown }) {
  const claimSet = readRecord(value);
  const claims = readArray(claimSet?.claims);
  if (!claimSet || claims.length === 0) return <JsonFallback value={value} />;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-10 pb-16">
      <div className="mt-4 border-b border-gray-200 pb-6">
        <h3 className="text-3xl font-bold text-gray-900">权利要求人工审核（已确认）</h3>
      </div>

      <div className="space-y-8">
        {claims.map((item, index) => {
          const claim = readRecord(item) ?? {};
          return (
            <div className="group" key={`claim-readonly-${index}`}>
              <div className="mb-3 flex items-center gap-3">
                <span className="text-lg font-bold text-gray-800">{toText(claim.claim_number)}.</span>
                {claim.claim_type === "independent" ? (
                  <span className="rounded border border-gray-200 px-2 py-0.5 text-xs font-bold text-gray-500">独立权利要求</span>
                ) : (
                  <span className="rounded border border-gray-100 px-2 py-0.5 text-xs font-medium text-gray-400">从属权利要求</span>
                )}
              </div>
              <textarea
                className="min-h-[120px] w-full resize-y rounded-xl border border-gray-200 bg-gray-50/50 p-5 text-[15px] leading-relaxed text-gray-800 outline-none"
                readOnly
                spellCheck={false}
                value={toText(claim.full_text)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TraceabilityCheckView({ value }: { value: unknown }) {
  const data = readRecord(value);
  const reports = readArray(data?.reports);
  if (!data || reports.length === 0) return <JsonFallback value={value} />;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-12 pb-16">
      <div className="mt-4 border-b border-gray-200 pb-6">
        <h3 className="text-3xl font-bold text-gray-900">可追溯性检查</h3>
      </div>

      <section>
        <h4 className="mb-4 text-lg font-bold text-gray-800">全局风险评估</h4>
        <p className="text-[15px] leading-relaxed text-gray-700">{toText(data.overall_risk_assessment)}</p>
      </section>

      <section>
        <h4 className="mb-6 text-lg font-bold text-gray-800">逐项特征溯源</h4>
        <div className="space-y-12">
          {reports.map((reportItem, idx) => {
            const report = readRecord(reportItem) ?? {};
            const evidences = readArray(report.elements_evidence);
            const supported = report.is_fully_supported === true;
            return (
              <article className="border-t border-gray-100 pt-8 first:border-0 first:pt-0" key={`trace-report-${idx}`}>
                <div className="mb-6 flex items-center gap-4">
                  <h5 className="text-xl font-bold text-gray-900">权利要求 {toText(report.claim_number)}</h5>
                  {supported ? (
                    <span className="text-sm font-bold text-emerald-600">✓ 100% 支撑</span>
                  ) : (
                    <span className="text-sm font-bold text-red-600">⚠️ 存在超范围风险</span>
                  )}
                </div>

                <div className="space-y-8 pl-2">
                  {evidences.map((evidenceItem, eIdx) => {
                    const evidence = readRecord(evidenceItem) ?? {};
                    const supportLevel = toText(evidence.support_level);
                    const isExplicit = String(supportLevel).toLowerCase() === "explicit";
                    return (
                      <div className="space-y-3" key={`trace-evidence-${idx}-${eIdx}`}>
                        <div className="text-[15px] font-bold leading-relaxed text-gray-800">
                          <span className="mr-2 select-none font-normal text-gray-400">特征:</span>
                          {toText(evidence.feature_text)}
                        </div>

                        <div className="border-l-2 border-gray-200 pl-4 text-[14.5px] italic leading-relaxed text-gray-500">
                          <span className="mr-2 select-none not-italic text-gray-400">原文:</span>
                          "{toText(evidence.verbatim_quote)}"
                        </div>

                        <div className="mt-1 text-[15px] leading-relaxed text-gray-700">
                          <span className="mr-2 select-none font-semibold text-gray-800">结论:</span>
                          <span
                            className={`mr-2 rounded border px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wider ${
                              isExplicit ? "border-gray-300 text-gray-500" : "border-orange-200 text-orange-600"
                            }`}
                          >
                            {supportLevel}
                          </span>
                          {toText(evidence.reasoning)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function DraftSpecificationView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data || !data.title) return <JsonFallback value={value} />;

  const inventionContent = readRecord(data.invention_content) ?? {};
  const detail = readRecord(data.detailed_implementation) ?? {};
  const componentDetails = readArray(detail.component_details);

  const renderParagraph = (text: unknown) => (
    <p className="mb-4 indent-8 text-[15px] leading-[1.8] text-gray-800 text-justify">{toText(text)}</p>
  );

  return (
    <div className="mx-auto w-full max-w-5xl space-y-16 pb-24">
      <div className="mt-12 border-b-2 border-gray-900 pb-10 text-center">
        <h1 className="mb-4 text-4xl font-black leading-tight text-gray-900">{toText(data.title)}</h1>
        <div className="flex items-center justify-center gap-4 text-sm font-medium uppercase tracking-widest text-gray-500">
          <span>专利说明书草案</span>
          <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
          <span>系统自动生成</span>
        </div>
      </div>

      <section className="space-y-6">
        <h2 className="border-l-4 border-blue-600 pl-4 text-xl font-bold text-gray-900">技术领域</h2>
        {renderParagraph(data.technical_field)}

        <h2 className="mt-8 border-l-4 border-blue-600 pl-4 text-xl font-bold text-gray-900">背景技术</h2>
        {renderParagraph(data.background_art)}
      </section>

      <section className="space-y-6">
        <h2 className="border-l-4 border-blue-600 pl-4 text-xl font-bold text-gray-900">发明内容</h2>
        <div className="space-y-6 pl-2">
          <h3 className="text-[17px] font-bold text-gray-800">要解决的技术问题</h3>
          {renderParagraph(inventionContent.technical_problem)}

          <h3 className="text-[17px] font-bold text-gray-800">技术方案</h3>
          {renderParagraph(inventionContent.technical_solution)}

          <h3 className="text-[17px] font-bold text-gray-800">有益效果</h3>
          {renderParagraph(inventionContent.beneficial_effects)}
        </div>
      </section>

      {data.drawings_description ? (
        <section className="space-y-6">
          <h2 className="border-l-4 border-blue-600 pl-4 text-xl font-bold text-gray-900">附图说明</h2>
          {renderParagraph(data.drawings_description)}
        </section>
      ) : null}

      <section className="space-y-8">
        <h2 className="border-l-4 border-blue-600 pl-4 text-xl font-bold text-gray-900">具体实施方式</h2>
        <div className="space-y-10 pl-2">
          <div>
            {renderParagraph(detail.introductory_boilerplate)}
            {renderParagraph(detail.overall_architecture)}
          </div>

          {componentDetails.map((comp, idx) => {
            const c = readRecord(comp) ?? {};
            return (
              <div className="relative rounded-xl border border-gray-100 bg-gray-50/50 p-8" key={`spec-comp-${idx}`}>
                <div className="absolute -top-3 left-6 rounded bg-blue-100 px-3 py-1 text-xs font-black text-blue-800 shadow-sm">
                  特征 {idx + 1}
                </div>
                <h4 className="mb-6 mt-2 text-[17px] font-bold text-gray-900">{toText(c.feature_name)}</h4>
                <div className="space-y-4">
                  <div>
                    <span className="mb-1 block text-[15px] font-bold text-gray-700">【结构与连接关系】</span>
                    {renderParagraph(c.structure_and_connection)}
                  </div>
                  <div>
                    <span className="mb-1 block text-[15px] font-bold text-gray-700">【协同与工作机理】</span>
                    {renderParagraph(c.working_principle)}
                  </div>
                </div>
              </div>
            );
          })}

          {detail.workflow_description ? (
            <div className="mt-8">
              <h3 className="mb-4 text-[17px] font-bold text-gray-800">整体工作流程</h3>
              {renderParagraph(detail.workflow_description)}
            </div>
          ) : null}

          {detail.alternative_embodiments ? (
            <div className="mt-8">
              <h3 className="mb-4 text-[17px] font-bold text-gray-800">替代实施方案</h3>
              {renderParagraph(detail.alternative_embodiments)}
            </div>
          ) : null}
        </div>
      </section>

    </div>
  );
}

function LogicReviewView({
  value,
  showActions = false,
  busy = false,
  onExecuteRevision,
  onFinish,
}: {
  value: unknown;
  showActions?: boolean;
  busy?: boolean;
  onExecuteRevision?: (instruction: string) => void;
  onFinish?: () => void;
}) {
  const issues = readArray(value).filter((item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item));
  const hasIssues = issues.length > 0;
  const [customInstruction, setCustomInstruction] = useState("");

  return (
    <div className="mx-auto w-full max-w-5xl space-y-10 pb-24">
      <div className="mt-4 flex items-end justify-between border-b border-gray-200 pb-6">
        <div>
          <h3 className="text-3xl font-bold text-gray-900">逻辑审查</h3>
        </div>
      </div>

      {hasIssues ? (
        <div className="rounded-r-lg border-l-4 border-orange-400 bg-orange-50/80 p-5">
          <h4 className="flex items-center gap-2 text-[15px] font-bold text-orange-800">⚠️ 发现 {issues.length} 处逻辑支撑缺陷</h4>
          <p className="mt-1 text-sm text-orange-700">说明书未充分支撑部分特征。下游“说明书小改”将依据以下修复指令定向扩写。</p>
        </div>
      ) : (
        <div className="rounded-r-lg border-l-4 border-emerald-400 bg-emerald-50/80 p-5">
          <h4 className="flex items-center gap-2 text-[15px] font-bold text-emerald-800">✓ 逻辑审校通过</h4>
          <p className="mt-1 text-sm text-emerald-700">权利要求与说明书逻辑一致，未发现支撑冲突或遗漏。</p>
        </div>
      )}

      {hasIssues ? (
        <div className="mt-8 space-y-12">
          {issues.map((issue, idx) => {
            const severity = String(issue.severity ?? "medium").toLowerCase();
            const levelClass =
              severity === "high"
                ? "border-red-200 text-red-600 bg-red-50/50"
                : "border-orange-200 text-orange-600 bg-orange-50/50";
            return (
              <article className="border-t border-gray-100 pt-8 first:border-0 first:pt-0" key={`logic-issue-${idx}`}>
                <div className="mb-5 flex flex-wrap items-center gap-3">
                  <span className="text-xl font-bold text-gray-900">{toText(issue.claim_reference)}</span>
                  <span className={`rounded border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider ${levelClass}`}>
                    {severity} Risk
                  </span>
                  <span className="rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-[11px] font-semibold text-gray-500">
                    {toText(issue.issue_type)}
                  </span>
                </div>

                <div className="space-y-5 pl-2">
                  <div className="text-[15px] leading-relaxed text-gray-800 text-justify">
                    <span className="mr-2 select-none font-bold text-gray-900">缺陷描述:</span>
                    {toText(issue.description)}
                  </div>

                  <div className="rounded-r-lg border-l-4 border-blue-500 bg-blue-50/30 py-4 pl-4 pr-5 text-[15px] leading-relaxed text-gray-800 text-justify">
                    <span className="mb-2 flex select-none items-center gap-2 font-bold text-blue-700">✨ 机器修复指令</span>
                    <p className="font-medium text-gray-700">{toText(issue.patch_instruction)}</p>
                  </div>

                  {issue.suggestion ? (
                    <div className="text-[14px] leading-relaxed text-gray-500 text-justify">
                      <span className="mr-2 select-none font-semibold text-gray-600">修改建议:</span>
                      {toText(issue.suggestion)}
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {showActions ? (
        <div className="mt-12 border-t border-gray-200 pt-10">
          {hasIssues ? (
            <div className="space-y-6 rounded-xl border border-gray-100 bg-gray-50/50 p-8">
              <div>
                <h4 className="mb-2 flex items-center gap-2 text-[16px] font-bold text-gray-900">✍️ 人工审核</h4>
                <p className="mb-5 text-[14px] text-gray-500">
                  确认后系统将仅针对上述问题执行定向小改。你也可以在下方补充本轮修订指令。
                </p>
                <textarea
                  className="min-h-[120px] w-full resize-y rounded-xl border border-gray-200 bg-white p-5 text-[15px] leading-relaxed text-gray-800 outline-none transition-all hover:border-gray-300 focus:border-blue-400 focus:ring-4 focus:ring-blue-50"
                  onChange={(e) => setCustomInstruction(e.target.value)}
                  placeholder="可选：补充本轮修订指令..."
                  value={customInstruction}
                />
              </div>
              <div className="flex justify-end">
                <button
                  className="transform rounded-lg bg-blue-600 px-8 py-3 text-[15px] font-bold text-white shadow-[0_4px_12px_rgba(37,99,235,0.2)] transition-all hover:-translate-y-0.5 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={busy}
                  onClick={() => onExecuteRevision?.(customInstruction)}
                  type="button"
                >
                  确认并执行说明书定向小改
                </button>
              </div>
            </div>
          ) : (
            <div className="flex justify-end">
              <button
                className="transform rounded-lg bg-emerald-600 px-8 py-3 text-[15px] font-bold text-white shadow-[0_4px_12px_rgba(16,185,129,0.2)] transition-all hover:-translate-y-0.5 hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
                onClick={() => onFinish?.()}
                type="button"
              >
                无缺陷，完成说明书撰写流程
              </button>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function DrawingAnalysisView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const figures = readArray(data.figures);
  const warnings = readArray(data.warnings);
  const overallNotes = data.overall_notes;
  const imageMetas = readArray(sessionData?.disclosure_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );

  return (
    <div className="mx-auto w-full max-w-6xl space-y-12 pb-16">
      <div className="mt-2 border-b border-gray-200 pb-6">
        <h3 className="text-3xl font-bold text-gray-900">附图分析</h3>
      </div>

      {overallNotes ? (
        <section>
          <h4 className="mb-4 text-lg font-bold text-gray-800">分析总结</h4>
          <p className="text-[15px] leading-relaxed text-gray-700">{toText(overallNotes)}</p>
        </section>
      ) : null}

      {warnings.length > 0 ? (
        <section>
          <h4 className="mb-4 flex items-center gap-2 text-lg font-bold text-red-700">⚠️ 识别异常与冲突</h4>
          <ul className="ml-5 list-outside list-disc space-y-2 text-[15px] leading-relaxed text-red-600">
            {warnings.map((w, idx) => (
              <li className="pl-1" key={`warn-${idx}`}>{toText(w)}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h4 className="mb-6 text-lg font-bold text-gray-800">附图详细解析</h4>
        {figures.length > 0 ? (
          <div className="space-y-12">
            {figures.map((fig, idx) => {
              const figure = readRecord(fig) ?? {};
              const figureId = figure.figure_id ?? figure.figure_label ?? `图${idx + 1}`;
              const title = figure.title ?? "未命名图项";
              const summary = figure.summary ?? figure.description ?? "";
              const refs = readArray(figure.reference_numerals);
              const relations = readArray(figure.relations);
              const imageId = pickFigureImageId(figure, idx, imageMetas);
              const imageSrc = imageId ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(imageId)}` : null;

              return (
                <article className="border-t border-gray-100 pt-8 first:border-t-0 first:pt-0" key={`fig-${idx}`}>
                  <h5 className="mb-3 text-xl font-bold text-gray-900">
                    {toText(figureId)} <span className="mx-2 font-normal text-gray-400">|</span> {toText(title)}
                  </h5>

                  {imageSrc ? (
                    <div className="mb-5">
                      <img
                        alt={`${toText(figureId)} 缩略图`}
                        className="max-h-56 w-auto rounded-lg border border-gray-200 object-contain"
                        loading="lazy"
                        src={imageSrc}
                      />
                    </div>
                  ) : null}

                  <p className="mb-8 text-[15px] leading-relaxed text-gray-700">{toText(summary)}</p>

                  <div className="grid grid-cols-1 gap-10 lg:grid-cols-2">
                    <div>
                      <h6 className="mb-4 border-b border-gray-100 pb-2 text-sm font-bold uppercase tracking-wider text-gray-400">
                        提取标号与部件
                      </h6>
                      {refs.length > 0 ? (
                        <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
                          {refs.map((item, rIdx) => {
                            const ref = readRecord(item) ?? {};
                            const numeral = ref.numeral ?? ref.reference_numeral ?? ref.id ?? "-";
                            const partName = ref.part_name ?? ref.component_name ?? ref.name ?? "-";
                            return (
                              <div className="flex items-baseline gap-3 text-[15px]" key={`ref-${idx}-${rIdx}`}>
                                <span className="w-12 shrink-0 text-right font-mono font-semibold text-blue-600">{toText(numeral)}</span>
                                <span className="text-gray-700">{toText(partName)}</span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-[15px] italic text-gray-400">未提取到明显标号</p>
                      )}
                    </div>

                    <div>
                      <h6 className="mb-4 border-b border-gray-100 pb-2 text-sm font-bold uppercase tracking-wider text-gray-400">
                        隐含连接关系
                      </h6>
                      {relations.length > 0 ? (
                        <ul className="ml-5 list-outside list-disc space-y-3 text-[15px] leading-relaxed text-gray-700">
                          {relations.map((item, relIdx) => {
                            const rel = readRecord(item) ?? {};
                            const subject = rel.subject_numeral ?? rel.source_component ?? rel.subject ?? "-";
                            const predicate = rel.predicate ?? rel.connection_type ?? rel.relationship ?? "-";
                            const obj = rel.object_numeral ?? rel.target_component ?? rel.object ?? "-";
                            const evidence = rel.evidence ?? rel.reasoning ?? "";
                            return (
                              <li className="pl-1" key={`rel-${idx}-${relIdx}`}>
                                <span className="font-semibold text-gray-900">{toText(subject)}</span>
                                <span className="mx-2 text-sm text-gray-400">({toText(predicate)})</span>
                                <span className="font-semibold text-gray-900">{toText(obj)}</span>
                                {evidence ? <span className="mx-2 text-gray-400">—— {toText(evidence)}</span> : null}
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <p className="text-[15px] italic text-gray-400">未提取到显性拓扑关系</p>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-gray-500">暂无逐图结构化结果，显示原始输出如下。</p>
        )}
      </section>

      {figures.length === 0 ? <JsonFallback value={value} /> : null}
    </div>
  );
}

function TechExtractionSemanticView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const problems = readArray(data.background_and_core_problems);
  const features = readArray(data.detailed_features);
  const advantages = readArray(data.overall_advantages);
  const quotes = readArray(data.source_quotes);

  return (
    <div className="mx-auto w-full max-w-6xl space-y-10 pb-12">
      <div className="border-b border-gray-100 pb-4 pt-2">
        <h3 className="text-2xl font-bold text-gray-800">技术要点提取</h3>
      </div>

      <section>
        <h4 className="mb-4 text-lg font-bold text-gray-800">现有技术痛点</h4>
        <div className="space-y-3">
          {problems.length > 0 ? (
            problems.map((problem, idx) => (
              <div className="flex gap-3" key={`problem-${idx}`}>
                <span className="mt-1 shrink-0 text-gray-500">•</span>
                <p className="text-[15px] leading-relaxed text-gray-700">{toText(problem)}</p>
              </div>
            ))
          ) : (
            <p className="text-[15px] leading-relaxed text-gray-700">未识别到痛点列表。</p>
          )}
        </div>
      </section>

      <section>
        <h4 className="mb-4 text-lg font-bold text-gray-800">核心解决方案</h4>
        <p className="text-[15px] leading-relaxed text-gray-700">{toText(data.core_solution_overview)}</p>
      </section>

      <section>
        <h4 className="mb-4 text-lg font-bold text-gray-800">详细技术特征</h4>
        <div className="space-y-5">
          {features.map((feature, idx) => {
            const f = readRecord(feature) ?? {};
            return (
              <article
                className="rounded-xl border border-gray-200 bg-white p-5"
                key={`feature-${idx}`}
              >
                <div className="mb-3 flex items-center gap-2">
                  <span className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-bold text-gray-700">特征 {idx + 1}</span>
                  <h5 className="text-base font-bold text-gray-800">{toText(f.feature_name)}</h5>
                </div>
                <p className="mb-4 text-[15px] leading-relaxed text-gray-700">{toText(f.detailed_structure_or_step)}</p>
                <div className="space-y-3 border-t border-gray-100 pt-3">
                  <div className="flex items-start gap-2">
                    <span className="mt-1 shrink-0 text-gray-500">•</span>
                    <p className="text-[15px] leading-relaxed text-gray-700"><span className="font-medium text-gray-800">解决：</span>{toText(f.solved_sub_problem)}</p>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="mt-1 shrink-0 text-gray-500">•</span>
                    <p className="text-[15px] leading-relaxed text-gray-700"><span className="font-medium text-gray-800">效果：</span>{toText(f.specific_effect)}</p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section>
        <h4 className="mb-4 text-lg font-bold text-gray-800">整体优势与创新</h4>
        <div className="space-y-3">
          {advantages.map((adv, idx) => (
            <div className="flex gap-3" key={`adv-${idx}`}>
              <span className="mt-1 shrink-0 text-gray-500">•</span>
              <p className="text-[15px] leading-relaxed text-gray-700">{toText(adv)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="pt-2">
        <details className="group">
          <summary className="cursor-pointer select-none text-lg font-bold text-gray-800">
            点击查看交底书原话摘抄溯源
          </summary>
          <div className="mt-3 space-y-3 border-l-2 border-gray-200 pl-3">
            {quotes.map((q, idx) => (
              <p className="text-[13px] italic leading-relaxed text-gray-500" key={`q-${idx}`}>{toText(q)}</p>
            ))}
          </div>
        </details>
      </section>
    </div>
  );
}

function DraftDiagnosticAnalyzerView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;
  const imageMetas = readArray(sessionData?.application_images_meta)
    .map((item) => readRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null);
  const getFigureImageUrlPlaceholder = (figLabel: string): string => {
    const cleanLabel = figLabel.replace("图", "Fig.");
    return `https://dummyimage.com/600x450/f8fafc/334155.png&text=Draft+${encodeURIComponent(cleanLabel)}`;
  };

  const broadClaimFlaws = readArray(data.broad_claim_flaws);
  const dependentClaimFaults = readArray(data.dependent_claim_faults);
  const effectDisconnects = readArray(data.effect_disconnects);
  const textVisualMismatches = readArray(data.text_visual_mismatches);

  return (
    <div className="mx-auto w-full max-w-6xl space-y-16 pb-24">
      <div className="mt-4 border-b border-gray-900 pb-6">
        <h3 className="text-3xl font-black tracking-tight text-gray-900">申请文件分析</h3>
      </div>

      {data.global_diagnosis_summary ? (
        <section>
          <h4 className="mb-4 flex items-center gap-2 text-xl font-bold text-gray-900">全局诊断</h4>
          <p className="text-[15px] leading-relaxed text-gray-700 text-justify">{toText(data.global_diagnosis_summary)}</p>
        </section>
      ) : null}

      {broadClaimFlaws.length > 0 ? (
        <section>
          <h4 className="mb-6 text-xl font-bold text-gray-900">独立权利要求诊断</h4>
          <div className="space-y-8">
            {broadClaimFlaws.map((flaw, idx) => {
              const f = readRecord(flaw) ?? {};
              return (
                <div className="border-t border-gray-100 pt-6" key={`broad-${idx}`}>
                  <div className="mb-4 flex items-center gap-3">
                    <span className="rounded border border-gray-300 px-3 py-1 font-mono text-[14px] font-bold text-gray-800">
                      权利要求 {toText(f.claim_number)}
                    </span>
                  </div>
                  <div className="space-y-4 pl-1">
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">缺陷描述:</span>
                      {toText(f.flaw_description)}
                    </p>
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">缺失拓扑约束:</span>
                      {toText(f.missing_topological_constraint)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {dependentClaimFaults.length > 0 ? (
        <section>
          <h4 className="mb-6 text-xl font-bold text-gray-900">从属权利要求诊断</h4>
          <div className="space-y-8">
            {dependentClaimFaults.map((fault, idx) => {
              const f = readRecord(fault) ?? {};
              return (
                <div className="border-t border-gray-100 pt-6" key={`dep-${idx}`}>
                  <div className="mb-4 flex items-center gap-3">
                    <span className="rounded border border-gray-300 px-3 py-1 font-mono text-[14px] font-bold text-gray-800">
                      权利要求 {toText(f.claim_number)}
                    </span>
                  </div>
                  <div className="space-y-4 pl-1">
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">无效限定分析:</span>
                      {toText(f.trivial_limitation)}
                    </p>
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">建议升级方向:</span>
                      {toText(f.upgrade_direction)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {effectDisconnects.length > 0 ? (
        <section>
          <h4 className="mb-6 text-xl font-bold text-gray-900">说明书结构与效果分析</h4>
          <div className="space-y-8">
            {effectDisconnects.map((item, idx) => {
              const e = readRecord(item) ?? {};
              return (
                <div className="border-t border-gray-100 pt-6" key={`eff-dis-${idx}`}>
                  <div className="mb-4 flex items-center gap-3">
                    <span className="text-[15px] font-bold text-gray-900">目标溯源：{toText(e.source_location)}</span>
                  </div>
                  <div className="space-y-4 border-l-2 border-gray-200 pl-6">
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">干瘪结构描述:</span>
                      {toText(e.dry_structure_mentioned)}
                    </p>
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">缺失技术效果:</span>
                      {toText(e.missing_technical_effect)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {textVisualMismatches.length > 0 ? (
        <section>
          <h4 className="mb-6 text-xl font-bold text-gray-900">图文信息失配</h4>
          <div className="space-y-12">
            {textVisualMismatches.map((item, idx) => {
              const m = readRecord(item) ?? {};
              const omission = toText(m.text_omission_description);
              const figureLabel = toText(m.figure_label);
              const imageId = pickFigureImageId({ figure_label: figureLabel, figure_id: figureLabel }, idx, imageMetas);
              const imageSrc = imageId
                ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(imageId)}`
                : getFigureImageUrlPlaceholder(figureLabel);
              return (
                <div className="border-t border-gray-100 pt-8 first:border-0 first:pt-0" key={`tv-${idx}`}>
                  <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
                    <div className="lg:col-span-4">
                      <div className="group relative aspect-[4/3] overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                        <img
                          alt={figureLabel}
                          className="h-full w-full object-contain p-2 transition-transform duration-300 group-hover:scale-105"
                          loading="lazy"
                          src={imageSrc}
                        />
                        <span className="absolute bottom-2 right-2 rounded bg-gray-900 px-2 py-0.5 font-mono text-[12px] font-bold text-white shadow">
                          {figureLabel}
                        </span>
                      </div>
                    </div>

                    <div className="space-y-6 pt-1 lg:col-span-8">
                      {omission && omission !== "未提供" && omission !== "当前节点暂无输出。" ? (
                        <div className="border-l-2 border-gray-300 pl-5">
                          <span className="mb-1 block text-[13px] font-bold uppercase tracking-wider text-gray-500">
                            文本遗漏
                          </span>
                          <p className="text-[15px] leading-relaxed text-gray-700 text-justify">{omission}</p>
                        </div>
                      ) : null}

                      <div className="border-l-4 border-gray-800 pl-5">
                        <span className="mb-2 flex items-center gap-1.5 text-[13px] font-bold uppercase tracking-wider text-gray-900">
                          视觉隐含的高价值证据
                        </span>
                        <p className="text-[15px] font-medium leading-relaxed text-gray-800 text-justify">
                          {toText(m.visual_goldmine_evidence)}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      
    </div>
  );
}

function extractFigureLabelsFromText(value: unknown): string[] {
  const raw = String(value ?? "").trim();
  if (!raw) return [];
  const normalized = raw.replace(/[，、；;]+/g, ",");
  const directMatches = normalized.match(/图\s*\d{1,3}/g) ?? [];
  const labels = directMatches
    .map((m) => m.replace(/\s+/g, ""))
    .filter((m) => m.length > 0);
  if (labels.length > 0) return Array.from(new Set(labels));
  if (normalized.includes("无")) return [];
  return [normalized];
}

function SynergyMinerView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;
  const imageMetas = readArray(sessionData?.application_images_meta)
    .map((item) => readRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null);
  const getFigureImageUrlPlaceholder = (figLabel: string): string => {
    const cleanLabel = figLabel ? figLabel.replace("图", "Fig.") : "Fig.";
    return `https://dummyimage.com/600x450/ffffff/333333.png&text=Draft+${encodeURIComponent(cleanLabel)}`;
  };

  const textDriven = readArray(data.text_driven_synergies);
  const visualDriven = readArray(data.visual_driven_synergies);

  const renderItem = (item: unknown, idx: number, prefix: string) => {
    const row = readRecord(item) ?? {};
    const sourceFigure = toText(row.source_figure);
    const figureLabels = extractFigureLabelsFromText(sourceFigure);
    const figureLabel = figureLabels[0] ?? sourceFigure;
    const imageId = pickFigureImageIdStrictByLabel(figureLabel, imageMetas);
    const imageSrc = imageId
      ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(imageId)}`
      : getFigureImageUrlPlaceholder(figureLabel);

    return (
      <div className="border-t border-gray-100 pt-10 first:border-0 first:pt-0" key={`${prefix}-${idx}`}>
        <div className="mb-8 flex flex-wrap items-center gap-4">
          <h5 className="text-lg font-bold text-gray-900">{toText(row.feature_name)}</h5>
          <div className="flex gap-2">
            <span className="rounded border border-gray-300 px-2 py-0.5 font-mono text-[13px] font-medium text-gray-600">
              溯源: {toText(row.source_paragraph)}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <div className="rounded border border-gray-200 bg-white p-1.5 shadow-sm">
              <img
                alt={sourceFigure}
                className="h-auto w-full border border-gray-50 object-contain"
                loading="lazy"
                src={imageSrc}
              />
            </div>
            <div className="mt-3 text-center">
              <span className="border-b-2 border-gray-900 pb-0.5 font-mono text-[13px] font-bold text-gray-700">
                锚点: {sourceFigure}
              </span>
            </div>
          </div>

          <div className="space-y-6 lg:col-span-8">
            <div className="border-l-2 border-gray-300 pl-5">
              <p className="font-serif text-[14.5px] italic leading-relaxed text-gray-500 text-justify">
                "{toText(row.verbatim_quote)}"
              </p>
            </div>

            <div className="space-y-5 pt-2">
              <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                <span className="mb-1 mr-2 block select-none font-bold text-gray-900">视觉特征</span>
                {toText(row.visual_morphology)}
              </p>
              <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                <span className="mb-1 mr-2 block select-none font-bold text-gray-900">结构协同</span>
                {toText(row.kinematic_synergy_mechanism)}
              </p>
              <p className="text-[15px] font-medium leading-relaxed text-gray-800 text-justify">
                <span className="mb-1 mr-2 block select-none font-bold text-gray-900">技术效果</span>
                {toText(row.derived_technical_effect)}
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-6xl space-y-20 pb-24">
      <div className="mt-4 border-b border-gray-900 pb-8">
        <h3 className="mb-6 text-3xl font-black tracking-tight text-gray-900">特征挖掘</h3>
        {data.vault_summary ? (
          <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
            <span className="mr-2 select-none font-bold text-gray-900">全局特征挖掘:</span>
            {toText(data.vault_summary)}
          </p>
        ) : null}
      </div>

      {textDriven.length > 0 ? (
        <section>
          <h4 className="mb-10 text-xl font-bold text-gray-900">基于文本的特征挖掘</h4>
          <div className="space-y-16">{textDriven.map((item, idx) => renderItem(item, idx, "txt"))}</div>
        </section>
      ) : null}

      {visualDriven.length > 0 ? (
        <section className="pt-8">
          <h4 className="mb-10 text-xl font-bold text-gray-900">基于视觉的特征挖掘</h4>
          <div className="space-y-16">{visualDriven.map((item, idx) => renderItem(item, idx, "vis"))}</div>
        </section>
      ) : null}

    </div>
  );
}

function ClaimArchitectView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const claims = readArray(data.reconstructed_claims);
  if (claims.length === 0) return <JsonFallback value={value} />;

  const fullText = typeof data.full_optimized_claims_text === "string" ? data.full_optimized_claims_text : "";
  const finalClaimsArray = fullText ? fullText.split("\n") : [];
  const globalA33 = toText(data.article_33_basis);

  const copyFullText = async () => {
    if (!fullText || !navigator?.clipboard) return;
    try {
      await navigator.clipboard.writeText(fullText);
    } catch {
      // no-op
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl space-y-16 pb-24">
      <div className="mt-4 border-b border-gray-900 pb-6">
        <h3 className="mb-6 text-3xl font-black tracking-tight text-gray-900">权利要求润色</h3>
      </div>

      {(data.independent_claim_strategy || data.dependent_claim_hierarchy) ? (
        <section className="space-y-6">
          <h4 className="mb-6 text-xl font-bold text-gray-900">润色策略</h4>
          <div className="space-y-5">
            {data.independent_claim_strategy ? (
              <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                <span className="mr-2 select-none font-bold text-gray-900">独立权项润色:</span>
                {toText(data.independent_claim_strategy)}
              </p>
            ) : null}
            {data.dependent_claim_hierarchy ? (
              <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                <span className="mr-2 select-none font-bold text-gray-900">从属权项润色:</span>
                {toText(data.dependent_claim_hierarchy)}
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section>
        <h4 className="mb-8 border-b border-gray-200 pb-4 text-xl font-bold text-gray-900">权利要求逐项分析</h4>
        <div className="space-y-16">
          {claims.map((claimItem, idx) => {
            const claim = readRecord(claimItem) ?? {};
            const dependencies = readArray(claim.dependencies).map((d) => toText(d)).filter((d) => d !== "当前节点暂无输出。");
            const isIndependent = dependencies.length === 0;
            const dependencyText = isIndependent ? "独立权利要求" : `引用权利要求 ${dependencies.join(", ")}`;

            return (
              <div className="space-y-6" key={`claim-arch-${idx}`}>
                <div className="mb-2 flex items-center gap-3">
                  <span className="rounded-sm border border-gray-900 px-3 py-1 font-mono text-[15px] font-bold uppercase tracking-wider text-gray-900">
                    Claim {toText(claim.claim_number)}
                  </span>
                  <span className="text-[14px] font-medium text-gray-500">{dependencyText}</span>
                </div>

                <div className="border-l-4 border-gray-800 py-1 pl-6">
                  <p className="font-serif text-[15px] font-medium leading-relaxed text-gray-900 text-justify">{toText(claim.claim_text)}</p>
                </div>

                <div className="space-y-5 pl-6 pt-2">
                  <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                    <span className="mb-1 mr-2 block select-none font-bold text-gray-900">加入协同机理:</span>
                    {toText(claim.injected_synergy_mechanism)}
                  </p>
                  <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                    <span className="mb-1 mr-2 block select-none font-bold text-gray-900">创造性依据:</span>
                    {toText(claim.inventiveness_defense)}
                  </p>
                  <p className="font-serif text-[14.5px] italic leading-relaxed text-gray-500 text-justify">
                    <span className="mb-1 mr-2 block select-none font-bold text-gray-600">A33 支撑溯源:</span>
                    {toText(claim.article_33_basis)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="border-t border-gray-900 pt-16">
        <div className="mb-8 flex items-center justify-between">
          <h4 className="text-xl font-bold text-gray-900">权利要求书完整草案</h4>
          <button
            className="flex items-center gap-1.5 rounded border border-gray-300 px-4 py-1.5 text-[14px] font-bold text-gray-700 transition-colors hover:border-gray-500"
            onClick={() => void copyFullText()}
            type="button"
          >
            一键复制全文
          </button>
        </div>

        <div className="mx-auto mb-10 max-w-4xl border border-gray-200 p-10 shadow-sm">
          <div className="space-y-6">
            {finalClaimsArray.length > 0 ? (
              finalClaimsArray.map((claimText, idx) => (
                <p className="font-serif text-[15.5px] leading-[1.9] text-gray-900 text-justify" key={`claim-final-${idx}`}>
                  {claimText}
                </p>
              ))
            ) : (
              <p className="font-serif text-[15.5px] leading-[1.9] text-gray-900 text-justify">{toText(data.full_optimized_claims_text)}</p>
            )}
          </div>
        </div>

        {globalA33 && globalA33 !== "当前节点暂无输出。" ? (
          <div className="mx-auto max-w-4xl border-l-2 border-gray-400 pl-5">
            <p className="text-[14px] italic leading-relaxed text-gray-500 text-justify">
              <span className="mr-2 select-none font-bold text-gray-600">全局合规确认:</span>
              "{globalA33}"
            </p>
          </div>
        ) : null}
      </section>

    </div>
  );
}

function SpecificationAmplifierView({ value }: { value: unknown }) {
  const data = readRecord(value);
  if (!data) return <JsonFallback value={value} />;

  const amplifiedParagraphs = readArray(data.amplified_paragraphs);
  const fullSpecText = typeof data.full_amplified_specification === "string" ? data.full_amplified_specification : "";
  const fullSpecArray = fullSpecText ? fullSpecText.split("\n") : [];

  const copyFullSpec = async () => {
    if (!fullSpecText || !navigator?.clipboard) return;
    try {
      await navigator.clipboard.writeText(fullSpecText);
    } catch {
      // no-op
    }
  };

  const isLikelyHeading = (line: string): boolean => {
    const t = line.trim();
    if (!t) return false;
    if (t.length > 18) return false;
    if (/^[\[(【（]/.test(t)) return false;
    if (/[，。；：,.!?]/.test(t)) return false;
    return true;
  };

  return (
    <div className="mx-auto w-full max-w-6xl space-y-20 pb-24">
      <div className="mt-4 border-b border-gray-900 pb-8">
        <h3 className="mb-6 text-3xl font-black tracking-tight text-gray-900">说明书润色</h3>
      </div>

      {data.background_problem_reframing ? (
        <section className="space-y-6">
          <h4 className="mb-6 text-xl font-bold text-gray-900">针对背景技术缺陷的润色</h4>
          <div className="border-l-2 border-gray-300 pl-6">
            <p className="font-serif text-[15px] leading-relaxed text-gray-700 text-justify">{toText(data.background_problem_reframing)}</p>
          </div>
        </section>
      ) : null}

      <section>
        <h4 className="mb-10 border-b border-gray-200 pb-4 text-xl font-bold text-gray-900">权利要求支撑扩写</h4>
        <div className="space-y-16">
          {amplifiedParagraphs.map((paraItem, idx) => {
            const para = readRecord(paraItem) ?? {};
            return (
              <div className="space-y-8" key={`amp-para-${idx}`}>
                <div className="flex items-center gap-3">
                  <span className="rounded-sm border border-gray-900 px-3 py-1 font-mono text-[14px] font-bold uppercase tracking-wider text-gray-900">
                    支撑目标: Claim {toText(para.supported_claim_number)}
                  </span>
                </div>

                <div className="border-l-4 border-gray-800 py-2 pl-6">
                  <span className="mb-3 block select-none text-[13px] font-bold uppercase tracking-wider text-gray-400">
                    拟注入说明书正文
                  </span>
                  <p className="font-serif text-[15.5px] font-medium leading-relaxed text-gray-900 text-justify">{toText(para.injected_text_snippet)}</p>
                </div>

                <div className="space-y-6 pl-6 pt-2">
                  <div className="flex items-start gap-3">
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">结构协同机理:</span>
                      {toText(para.core_mechanism)}
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <p className="text-[15px] leading-relaxed text-gray-700 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">动态作用:</span>
                      {toText(para.dynamic_action_description)}
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <p className="text-[15px] font-medium leading-relaxed text-gray-800 text-justify">
                      <span className="mr-2 select-none font-bold text-gray-900">预料不到的技术效果:</span>
                      {toText(para.unexpected_technical_effect)}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="border-t border-gray-900 pt-16">
        <div className="mb-10 flex items-center justify-between">
          <h4 className="text-xl font-bold text-gray-900">说明书定稿</h4>
          <button
            className="flex items-center gap-1.5 rounded border border-gray-300 px-4 py-1.5 text-[14px] font-bold text-gray-700 transition-colors hover:border-gray-500"
            onClick={() => void copyFullSpec()}
            type="button"
          >
            一键复制全案
          </button>
        </div>

        <div className="mx-auto mb-10 max-w-4xl border border-gray-200 p-12 shadow-sm">
          <div className="space-y-4">
            {fullSpecArray.length > 0 ? (
              fullSpecArray.map((line, idx) =>
                isLikelyHeading(line) ? (
                  <h5 className="pb-2 pt-6 text-center text-[16px] font-bold tracking-widest text-gray-900" key={`spec-line-h-${idx}`}>
                    {line}
                  </h5>
                ) : (
                  <p className="font-serif text-[15px] leading-[2] text-gray-800 text-justify" key={`spec-line-p-${idx}`}>
                    {line}
                  </p>
                ),
              )
            ) : (
              <p className="font-serif text-[15px] leading-[2] text-gray-800 text-justify">{toText(data.full_amplified_specification)}</p>
            )}
          </div>
        </div>
      </section>

    </div>
  );
}

function AdversarialReviewerView({
  value,
  sessionData,
}: {
  value: unknown;
  sessionData: Record<string, unknown> | null;
}) {
  const data = readRecord(value);
  if (!data || !Array.isArray(data.anti_hallucination_findings)) {
    return <div className="p-8 text-center text-gray-500">加载反幻觉审计数据中...</div>;
  }

  const extractFigureLabel = (textRaw: unknown): string => {
    const text = String(textRaw ?? "");
    if (!text) return "Fig.";
    const match = text.match(/(?:附?图)\s*(\d+(?:-\d+)?)/);
    return match ? `Fig. ${match[1]}` : "Fig.";
  };

  const getWireframePlaceholder = (figLabel: string): string =>
    `https://dummyimage.com/600x400/ffffff/9ca3af.png&text=${encodeURIComponent(figLabel + " Wireframe")}`;

  const getRiskBadge = (riskLevelRaw: unknown) => {
    const riskLevel = String(riskLevelRaw ?? "UNKNOWN").toUpperCase();
    let style = "border-gray-300 text-gray-500";
    if (riskLevel === "LOW") style = "border-emerald-400 text-emerald-700";
    if (riskLevel === "HIGH") style = "border-red-400 text-red-700 font-bold";
    return (
      <span className={`rounded border px-2.5 py-0.5 font-mono text-[12px] uppercase tracking-widest ${style}`}>
        RISK: {riskLevel}
      </span>
    );
  };

  const getBasisBadge = (isFoundRaw: unknown, label: string) => {
    const isFound = isFoundRaw === true;
    return (
      <span
        className={`rounded border px-2 py-0.5 text-[12px] font-bold uppercase tracking-wide ${
          isFound ? "border-gray-800 text-gray-900" : "border-dashed border-gray-300 text-gray-400"
        }`}
      >
        {isFound ? `[✓] ${label}` : `[✗] ${label} MISSING`}
      </span>
    );
  };

  const findings = readArray(data.anti_hallucination_findings);
  const issues = readArray(data.issues);
  const passGate = data.pass_gate === true;
  const appMetas = readArray(sessionData?.application_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );
  const priorMetas = readArray(sessionData?.prior_art_images_meta).filter(
    (m): m is Record<string, unknown> => !!m && typeof m === "object" && !Array.isArray(m),
  );
  const allMetas = [...appMetas, ...priorMetas];

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in-up pb-32 font-sans text-gray-800">
      <div className="mt-10 mb-16 border-b border-gray-200 pb-12">
        <h2 className="mb-8 text-3xl font-bold tracking-tight text-gray-900">逻辑审查</h2>

        <div className="mb-8 flex items-center gap-4">
          <span className="text-[14.5px] font-bold uppercase tracking-widest text-gray-900">全局结论：</span>
          <span className={`border-2 px-3 py-1 text-[14px] font-black uppercase tracking-widest ${passGate ? "border-gray-900 text-gray-900" : "border-red-700 text-red-700"}`}>
            {passGate ? "审核通过" : "拦截打回"}
          </span>
        </div>

        <div className="space-y-4 border-l-[3px] border-gray-900 pl-5">
          <div>
            <strong className="mb-1 block text-[14.5px] uppercase tracking-widest text-gray-900">最终判定：</strong>
            <p className="font-serif text-[15.5px] leading-[1.8] text-gray-800 text-justify">{toText(data.final_judgement)}</p>
          </div>
          <div className="border-t border-gray-200/50 pt-2">
            <strong className="mb-1 block text-[14px] text-gray-600">执行指令：</strong>
            <p className="text-[14.5px] font-bold text-gray-900">{toText(data.return_instruction)}</p>
          </div>
        </div>
      </div>

      <div className="mb-24 space-y-16">
        <h3 className="border-b border-gray-100 pb-4 text-xl font-bold uppercase tracking-wide text-gray-900">
          特征审查
        </h3>

        <div className="space-y-24 pl-2">
          {findings.map((finding, idx) => {
            const f = readRecord(finding) ?? {};
            const figLabel = extractFigureLabel(f.audit_reasoning ?? f.injected_mechanism);
            const figCandidate = figLabel.replace("Fig.", "图").trim();
            const strictImageId = pickFigureImageIdStrictByLabel(figCandidate, allMetas);
            const fallbackImageId = pickFigureImageId(
              { figure_label: figCandidate, figure_id: figCandidate },
              idx,
              allMetas,
            );
            const placeholderSrc = getWireframePlaceholder(figLabel);
            const primaryImageSrc = strictImageId
              ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(strictImageId)}`
              : fallbackImageId
                ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                : placeholderSrc;
            const secondaryImageSrc =
              strictImageId && fallbackImageId && strictImageId !== fallbackImageId
                ? `${API_BASE_URL}/api/v1/images/${encodeURIComponent(fallbackImageId)}`
                : null;
            return (
              <div className="space-y-8" key={`polish-logic-finding-${idx}`}>
                <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
                  <div className="space-y-4 lg:col-span-4">
                    <div className="border border-gray-200 bg-white p-2">
                      <img
                        src={primaryImageSrc}
                        alt={`Traceability ${figLabel}`}
                        className="h-auto w-full object-cover grayscale mix-blend-multiply opacity-80"
                        loading="lazy"
                        onError={(e) => {
                          const img = e.currentTarget;
                          if (secondaryImageSrc && img.src !== secondaryImageSrc) {
                            img.src = secondaryImageSrc;
                            return;
                          }
                          if (img.src !== placeholderSrc) {
                            img.src = placeholderSrc;
                            return;
                          }
                          img.onerror = null;
                        }}
                      />
                    </div>
                    <div className="flex items-baseline justify-between border-b border-gray-300 pb-1">
                      <span className="text-[13px] font-bold uppercase tracking-wide text-gray-900">{figLabel}</span>
                    </div>
                  </div>

                  <div className="space-y-6 lg:col-span-8">
                    <div className="mb-2 flex flex-wrap gap-3">
                      {getRiskBadge(f.hallucination_risk_level)}
                    </div>

                    <div className="text-[15.5px] leading-[1.8] text-gray-800 text-justify">
                      <strong className="mb-2 block border-b border-gray-200 pb-1 text-gray-900">特征：</strong>
                      <span className="font-serif">{toText(f.injected_mechanism)}</span>
                    </div>

                    <div className="mt-6 border-l-2 border-gray-300 pl-5">
                      <strong className="mb-2 block text-[14.5px] text-gray-900">溯源核对：</strong>
                      <p className="font-serif text-[15px] italic leading-[1.8] text-gray-700 text-justify">{toText(f.audit_reasoning)}</p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-20 border-t border-gray-200 pt-8">
        <h3 className="mb-6 text-xl font-bold uppercase tracking-widest text-gray-900">逻辑审查结论</h3>
        {issues.length > 0 ? (
          <div className="space-y-3 pl-2">
            {issues.map((issueItem, idx) => (
              <div className="border-l-2 border-gray-300 pl-4" key={`polish-logic-issue-${idx}`}>
                <p className="text-[14.5px] leading-relaxed text-gray-700">{toText(issueItem)}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-3 pl-2 font-serif italic text-gray-500">
            <span className="text-gray-400">↳</span>
            未检测到逻辑冲突或超范围。
          </div>
        )}
      </div>
    </div>
  );
}

export function NodeStageRenderer({
  mode,
  nodeId,
  nodeTitle,
  value,
  sessionData,
  showSpecReviewActions = false,
  busy = false,
  onExecuteRevision,
  onFinish,
}: NodeStageRendererProps) {
  if (mode === "home" || mode === "settings") return null;
  const showNodeMeta = nodeId === "upload";

  return (
    <section className="space-y-8 py-2">
      {showNodeMeta ? (
        <div>
          <h2 className="text-base font-semibold text-gray-800">{nodeTitle}</h2>
          <p className="mt-1 text-xs text-gray-500">节点 ID：{nodeId}</p>
        </div>
      ) : null}

      {mode === "draft" && nodeId === "extract_tech_node" ? <TechExtractionSemanticView value={value} /> : null}
      {mode === "draft" && nodeId === "drawing_analyze_node" ? <DrawingAnalysisView sessionData={sessionData} value={value} /> : null}
      {mode === "draft" && nodeId === "draft_claims_node" ? <DraftClaimsView value={value} /> : null}
      {mode === "draft" && nodeId === "traceability_check_node" ? <TraceabilityCheckView value={value} /> : null}
      {mode === "draft" && nodeId === "human_review_node" ? <ClaimsConfirmationReadonlyView value={value} /> : null}
      {mode === "draft" && nodeId === "write_spec_node" ? <DraftSpecificationView value={value} /> : null}
      {mode === "draft" && nodeId === "logic_review_node" ? (
        <LogicReviewView
          busy={busy}
          onExecuteRevision={onExecuteRevision}
          onFinish={onFinish}
          showActions={showSpecReviewActions}
          value={value}
        />
      ) : null}
      {mode === "oa" && nodeId === "application_baseline_agent" ? <ApplicationBaselineView value={value} /> : null}
      {mode === "oa" && nodeId === "oa_parser_node" ? <OaParserView sessionData={sessionData} value={value} /> : null}
      {mode === "oa" && nodeId === "multimodal_prior_art_agent" ? (
        <MultimodalVerificationView sessionData={sessionData} value={value} />
      ) : null}
      {mode === "oa" && nodeId === "concession_and_gap_node" ? <GapAnalysisView value={value} /> : null}
      {mode === "oa" && nodeId === "fallback_feature_miner_node" ? <FallbackFeatureMinerView value={value} /> : null}
      {mode === "oa" && nodeId === "prior_art_stress_tester_node" ? <PriorArtStressTesterView value={value} /> : null}
      {mode === "oa" && nodeId === "strategy_decision_node" ? <StrategyDecisionView value={value} /> : null}
      {mode === "oa" && nodeId === "claim_amendment_agent" ? <ClaimAmendmentView value={value} /> : null}
      {mode === "oa" && nodeId === "argument_writer_agent" ? <ArgumentWriterView value={value} /> : null}
      {mode === "oa" && nodeId === "spec_update_agent" ? <SpecUpdateView value={value} /> : null}
      {mode === "oa" && nodeId === "response_traceability_node" ? <FinalComplianceReviewView value={value} /> : null}
      {mode === "compare" && nodeId === "multimodal_draft_parser_node" ? (
        <MultimodalBaselineView sessionData={sessionData} value={value} />
      ) : null}
      {mode === "compare" && nodeId === "multimodal_prior_art_node" ? (
        <PriorArtAnatomyView sessionData={sessionData} value={value} />
      ) : null}
      {mode === "compare" && nodeId === "multimodal_matrix_comparison_node" ? <FeatureMatrixCollisionView value={value} /> : null}
      {mode === "compare" && nodeId === "risk_assessment_node" ? <RiskAssessmentView value={value} /> : null}
      {mode === "compare" && nodeId === "amendment_suggestion_node" ? <AmendmentSuggestionView value={value} /> : null}
      {mode === "polish" && nodeId === "multimodal_diagnostic_analyzer_node" ? (
        <DraftDiagnosticAnalyzerView sessionData={sessionData} value={value} />
      ) : null}
      {mode === "polish" && nodeId === "multimodal_synergy_miner_node" ? (
        <SynergyMinerView sessionData={sessionData} value={value} />
      ) : null}
      {mode === "polish" && nodeId === "claim_architect_node" ? <ClaimArchitectView value={value} /> : null}
      {mode === "polish" && nodeId === "specification_amplifier_node" ? <SpecificationAmplifierView value={value} /> : null}
      {mode === "polish" && nodeId === "multimodal_adversarial_reviewer_node" ? (
        <AdversarialReviewerView sessionData={sessionData} value={value} />
      ) : null}

      {!((mode === "draft" && nodeId === "extract_tech_node") ||
        (mode === "draft" && nodeId === "drawing_analyze_node") ||
        (mode === "draft" && nodeId === "draft_claims_node") ||
        (mode === "draft" && nodeId === "traceability_check_node") ||
        (mode === "draft" && nodeId === "human_review_node") ||
        (mode === "draft" && nodeId === "write_spec_node") ||
        (mode === "draft" && nodeId === "logic_review_node") ||
        (mode === "oa" && nodeId === "application_baseline_agent") ||
        (mode === "oa" && nodeId === "oa_parser_node") ||
        (mode === "oa" && nodeId === "multimodal_prior_art_agent") ||
        (mode === "oa" && nodeId === "concession_and_gap_node") ||
        (mode === "oa" && nodeId === "fallback_feature_miner_node") ||
        (mode === "oa" && nodeId === "prior_art_stress_tester_node") ||
        (mode === "oa" && nodeId === "strategy_decision_node") ||
        (mode === "oa" && nodeId === "claim_amendment_agent") ||
        (mode === "oa" && nodeId === "argument_writer_agent") ||
        (mode === "oa" && nodeId === "spec_update_agent") ||
        (mode === "oa" && nodeId === "response_traceability_node") ||
        (mode === "compare" && nodeId === "multimodal_draft_parser_node") ||
        (mode === "compare" && nodeId === "multimodal_prior_art_node") ||
        (mode === "compare" && nodeId === "multimodal_matrix_comparison_node") ||
        (mode === "compare" && nodeId === "risk_assessment_node") ||
        (mode === "compare" && nodeId === "amendment_suggestion_node") ||
        (mode === "polish" && nodeId === "multimodal_diagnostic_analyzer_node") ||
        (mode === "polish" && nodeId === "multimodal_synergy_miner_node") ||
        (mode === "polish" && nodeId === "claim_architect_node") ||
        (mode === "polish" && nodeId === "specification_amplifier_node") ||
        (mode === "polish" && nodeId === "multimodal_adversarial_reviewer_node")) ? (
        <JsonFallback value={value} />
      ) : null}
    </section>
  );
}
