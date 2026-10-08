import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type HitlStage = "claims_review" | "claims_revise_review" | "spec_review";

interface HitlActionPanelProps {
  visible: boolean;
  stage?: HitlStage;
  initialClaimsText?: string;
  initialRevisionInstruction?: string;
  busy?: boolean;
  onSubmitClaims: (approvedClaims: string) => void;
  onSubmitAutoReviseClaims: () => void;
  onSubmitSpecReview: (revisionInstruction: string) => void;
}

interface ClaimDraftItem {
  claim_number: number | string;
  claim_type?: string;
  depends_on?: unknown[];
  full_text: string;
  [key: string]: unknown;
}

function parseClaimsPayload(text: string): {
  root: Record<string, unknown> | null;
  claims: ClaimDraftItem[];
} {
  const trimmed = text.trim();
  if (!trimmed) return { root: null, claims: [] };
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (Array.isArray(parsed)) {
      const claims = parsed
        .filter((v) => !!v && typeof v === "object")
        .map((v, i) => {
          const row = v as Record<string, unknown>;
          return {
            ...row,
            claim_number: row.claim_number ?? i + 1,
            claim_type: typeof row.claim_type === "string" ? row.claim_type : "dependent",
            depends_on: Array.isArray(row.depends_on) ? row.depends_on : [],
            full_text: typeof row.full_text === "string" ? row.full_text : "",
          } as ClaimDraftItem;
        });
      return { root: { claims }, claims };
    }
    if (parsed && typeof parsed === "object") {
      const root = parsed as Record<string, unknown>;
      const list = Array.isArray(root.claims) ? root.claims : [];
      const claims = list
        .filter((v) => !!v && typeof v === "object")
        .map((v, i) => {
          const row = v as Record<string, unknown>;
          return {
            ...row,
            claim_number: row.claim_number ?? i + 1,
            claim_type: typeof row.claim_type === "string" ? row.claim_type : "dependent",
            depends_on: Array.isArray(row.depends_on) ? row.depends_on : [],
            full_text: typeof row.full_text === "string" ? row.full_text : "",
          } as ClaimDraftItem;
        });
      return { root, claims };
    }
  } catch {
    // fallback to raw textarea mode
  }
  return { root: null, claims: [] };
}

export function HitlActionPanel({
  visible,
  stage = "claims_review",
  initialClaimsText = "",
  initialRevisionInstruction = "",
  busy = false,
  onSubmitClaims,
  onSubmitAutoReviseClaims,
  onSubmitSpecReview,
}: HitlActionPanelProps) {
  const [approvedClaims, setApprovedClaims] = useState("");
  const [revisionInstruction, setRevisionInstruction] = useState("");
  const [claimItems, setClaimItems] = useState<ClaimDraftItem[]>([]);
  const [claimsRootTemplate, setClaimsRootTemplate] = useState<Record<string, unknown> | null>(null);
  const [autoReviseTriggered, setAutoReviseTriggered] = useState(false);

  useEffect(() => {
    if (visible) {
      setApprovedClaims(initialClaimsText);
      setRevisionInstruction(initialRevisionInstruction);
      const parsed = parseClaimsPayload(initialClaimsText);
      setClaimItems(parsed.claims);
      setClaimsRootTemplate(parsed.root);
      setAutoReviseTriggered(false);
    }
  }, [initialClaimsText, initialRevisionInstruction, visible]);

  if (!visible) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white/80 p-4 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">HITL 人工交互</h2>
        <p className="mt-2 text-sm text-slate-500">
          等待流程进入 <code>waiting_human</code> 节点。
        </p>
      </section>
    );
  }

  const canSubmitClaims = approvedClaims.trim().length > 0 && !busy;
  const canSubmitSpecReview = !busy;
  const hasTraceabilityIssues = stage === "claims_revise_review";
  const hasStructuredClaims = claimItems.length > 0;
  const hideSubmitInAutoReviseStage = hasTraceabilityIssues && (autoReviseTriggered || busy);

  const handleClaimTextChange = (index: number, newText: string) => {
    setClaimItems((prev) => prev.map((item, i) => (i === index ? { ...item, full_text: newText } : item)));
  };

  const submitEditedClaims = () => {
    if (!hasStructuredClaims) {
      onSubmitClaims(approvedClaims.trim());
      return;
    }
    const payload: Record<string, unknown> =
      claimsRootTemplate && typeof claimsRootTemplate === "object"
        ? { ...claimsRootTemplate, claims: claimItems }
        : { claims: claimItems };
    onSubmitClaims(JSON.stringify(payload, null, 2));
  };

  return (
    <section className="mx-auto w-full max-w-5xl space-y-10 pb-24">
      {stage === "claims_review" || stage === "claims_revise_review" ? (
        <>
          <div className="mt-4 border-b border-gray-200 pb-6">
            <h2 className="flex items-center gap-3 text-3xl font-bold text-gray-900">
              权利要求人工审核
              <span className="rounded bg-blue-100 px-2 py-1 text-[13px] font-semibold uppercase tracking-wider text-blue-700">
                HITL 确认节点
              </span>
            </h2>
            <p className="mt-3 text-[15px] text-gray-500">
              请审阅并定稿最终权利要求。可直接在下方文本框修改，确认后继续说明书流程。
            </p>
          </div>

          {hasTraceabilityIssues ? (
            <div className="flex items-start justify-between rounded-r-lg border-l-4 border-orange-400 bg-orange-50/80 p-5">
              <div>
                <h4 className="flex items-center gap-2 text-[15px] font-bold text-orange-800">⚠️ 发现潜在的超范围风险</h4>
                <p className="mt-1 text-sm text-orange-700">
                  可追溯性检查检测到部分特征可能无支撑。建议先执行自动小改，或手动删改后提交。
                </p>
              </div>
              <button
                className="ml-6 shrink-0 rounded-lg border border-orange-300 bg-white px-4 py-2 text-sm font-bold text-orange-600 shadow-sm transition-colors hover:bg-orange-50"
                disabled={busy}
                onClick={() => {
                  setAutoReviseTriggered(true);
                  onSubmitAutoReviseClaims();
                }}
                type="button"
              >
                {busy || autoReviseTriggered ? "处理中..." : "✨ 权利要求自动小改"}
              </button>
            </div>
          ) : (
            <div className="rounded-r-lg border-l-4 border-emerald-400 bg-emerald-50/80 p-5">
              <h4 className="flex items-center gap-2 text-[15px] font-bold text-emerald-800">✓ 追溯性检查通过</h4>
              <p className="mt-1 text-sm text-emerald-700">当前权利要求具备明确原文支撑，可直接提交或进行语句微调。</p>
            </div>
          )}

          {hasStructuredClaims ? (
            <div className="space-y-8">
              {claimItems.map((claim, index) => (
                <div className="group" key={`claim-editor-${index}`}>
                  <div className="mb-3 flex items-center gap-3">
                    <span className="text-lg font-bold text-gray-800">{claim.claim_number}.</span>
                    {claim.claim_type === "independent" ? (
                      <span className="rounded border border-gray-200 px-2 py-0.5 text-xs font-bold text-gray-500">独立权利要求</span>
                    ) : (
                      <span className="rounded border border-gray-100 px-2 py-0.5 text-xs font-medium text-gray-400">从属权利要求</span>
                    )}
                  </div>
                  <textarea
                    className="min-h-[120px] w-full resize-y rounded-xl border border-transparent bg-gray-50/50 p-5 text-[15px] leading-relaxed text-gray-800 outline-none transition-all hover:border-gray-200 hover:bg-gray-50 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-50"
                    onChange={(e) => handleClaimTextChange(index, e.target.value)}
                    spellCheck={false}
                    value={claim.full_text}
                  />
                </div>
              ))}
            </div>
          ) : (
            <textarea
              className="min-h-[160px] w-full resize-y rounded-xl border border-gray-200 bg-white p-4 text-sm leading-relaxed text-gray-800 outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-50"
              onChange={(event) => setApprovedClaims(event.target.value)}
              placeholder="请粘贴或编辑权利要求 JSON..."
              value={approvedClaims}
            />
          )}

          <div className="mt-12 flex justify-end border-t border-gray-200 pt-8">
            <button
              className="transform rounded-lg bg-blue-600 px-8 py-3 text-[15px] font-bold text-white shadow-[0_4px_12px_rgba(37,99,235,0.2)] transition-all hover:-translate-y-0.5 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={hideSubmitInAutoReviseStage || busy || (!hasStructuredClaims && !canSubmitClaims)}
              hidden={hideSubmitInAutoReviseStage}
              onClick={submitEditedClaims}
              type="button"
            >
              提交已确认权利要求
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="mt-2 text-sm text-amber-800">
            逻辑审校发现说明书问题。确认后将仅针对这些问题执行小范围修订，并自动复检。
          </p>
          <textarea
            className="mt-3 h-24 w-full resize-y rounded-xl border border-amber-300 bg-white p-3 text-sm text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
            onChange={(event) => setRevisionInstruction(event.target.value)}
            placeholder="可选：补充本轮修订指令。"
            value={revisionInstruction}
          />
          <div className="mt-3 flex justify-end">
            <Button
              disabled={!canSubmitSpecReview}
              onClick={() => {
                onSubmitSpecReview(revisionInstruction.trim());
              }}
            >
              确认并执行说明书小改
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
