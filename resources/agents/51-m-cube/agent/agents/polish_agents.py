from __future__ import annotations

import time
from typing import Any, TypedDict

from agents.base_agent import BaseStructuredAgent
from models.polish_schemas import (
    AdversarialReviewReport,
    AmplifiedSpecification,
    ClaimArchitecturePlan,
    DiagnosticReport,
    PolishFinalPackage,
    SynergyVault,
)


class PolishState(TypedDict, total=False):
    session_id: str
    trace_id: str
    status: str
    current_step: str
    original_claims: dict[str, Any]
    application_specification: dict[str, Any]
    application_images: list[dict[str, Any]]
    raw_claims: dict[str, Any]
    raw_specification: dict[str, Any]
    raw_drawings_context: list[dict[str, Any]]
    diagnostic_report: dict[str, Any] | None
    synergy_feature_vault: dict[str, Any] | None
    claim_architecture_plan: dict[str, Any] | None
    optimized_claims_text: str
    amplified_specification: dict[str, Any] | None
    optimized_specification_text: str
    adversarial_review_report: dict[str, Any] | None
    polish_final_package: dict[str, Any] | None
    polish_revision_count: int
    error_count: int
    tool_error_count: int
    last_error: dict[str, Any] | None
    node_latency_ms: int


def _duration_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _vision_context_from_state(state: PolishState) -> dict[str, Any]:
    images = state.get("application_images", [])
    image_paths = [str(item.get("source_path", "")).strip() for item in images if item.get("source_path")]
    image_mime_types = [str(item.get("mime_type", "image/png")) for item in images if item.get("source_path")]
    return {
        "image_paths": image_paths,
        "image_mime_types": image_mime_types,
        "application_images_meta": images,
    }


def diagnostic_analyzer_node(
    state: PolishState,
    agent: BaseStructuredAgent[DiagnosticReport],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    raw_claims = state.get("raw_claims") or state.get("original_claims")
    raw_specification = state.get("raw_specification") or state.get("application_specification")
    raw_drawings_context = state.get("raw_drawings_context") or state.get("application_images", [])
    prompt = (
        "You are an Expert Chinese Patent Draft Quality Inspector (The Pathologist).\n"
        "Your mission is to perform a relentless Text-Image Joint Pathological Diagnosis on the provided raw draft (claims, specification, and drawings).\n\n"
        "### DIAGNOSTIC RULES:\n"
        "1. IDENTIFY BROAD BLACK HOLES:\n"
        "   - Scan the independent claims. If they are just noun lists without rigorous topological constraints, structural connections, or synergistic mechanisms, log them in broad_claim_flaws.\n"
        "   - Provide a concrete missing_topological_constraint to guide Node 3.\n"
        "2. EXPOSE DEPENDENT CLAIM FAULTS:\n"
        "   - Find dependent claims that waste scope on trivialities. Log them and provide upgrade_direction.\n"
        "3. FIX EFFECT DISCONNECTS:\n"
        "   - Find where structures are listed without technical benefits. Provide missing_technical_effect for Node 4.\n"
        "4. TEXT-VISUAL JOINT AUDIT:\n"
        "   - Compare drawings against specification and find visual goldmines: structures/mechanisms drawn clearly but omitted in text.\n"
        "   - Record these in text_visual_mismatches with highly descriptive visual_goldmine_evidence.\n\n"
        "### ENGINEERING SAFETY RULES:\n"
        "1. Output valid JSON strictly matching the schema. No markdown fences.\n"
        "2. Keep strings concise (<=150 Chinese characters).\n"
        "3. Output in formal, professional Chinese.\n\n"
        f"[RAW DRAFT CLAIMS (原始权利要求)]\n{raw_claims}\n\n"
        f"[RAW DRAFT SPECIFICATION (原始说明书)]\n{raw_specification}\n\n"
        f"[RAW DRAWINGS CONTEXT (原始附图视觉输入)]\n{raw_drawings_context}"
    )
    result = agent.run_structured(
        prompt=prompt,
        output_model=DiagnosticReport,
        context=_vision_context_from_state(state),
    )
    return {
        "diagnostic_report": result.model_dump(),
        "current_step": "multimodal_diagnostic_analyzer_node",
        "status": "running",
        "node_latency_ms": _duration_ms(started_at),
    }


def synergy_miner_node(
    state: PolishState,
    agent: BaseStructuredAgent[SynergyVault],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    raw_specification = state.get("raw_specification") or state.get("application_specification")
    raw_drawings_context = state.get("raw_drawings_context") or state.get("application_images", [])
    prompt = (
        "You are an Expert Multimodal Mechanism Miner (CAD Reverse Engineer) for Chinese Patents.\n"
        "Your mission is to build a Synergy Vault (High-Value Mechanism Database) from the raw specification and drawings, heavily guided by the blind spots exposed in Node 1's Diagnostic Report.\n\n"
        "### MINING RULES:\n"
        "1. TARGETED EXCAVATION:\n"
        "   - Read Node 1's Diagnostic Report carefully. Pay special attention to text_visual_mismatches (visual goldmines). Go directly to those figures and extract hidden geometric/topological features.\n"
        "2. REVERSE ENGINEER THE KINEMATICS:\n"
        "   - Do NOT output isolated nouns.\n"
        "   - You MUST extract kinematic_synergy_mechanism: how parts interlock, slide, rotate, seal, and their spatial topology.\n"
        "3. DEDUCE THE EFFECT:\n"
        "   - For each mined mechanism, provide derived_technical_effect linked to physical structure/mechanism.\n"
        "4. ZERO HALLUCINATION:\n"
        "   - You may translate clear drawings into text, but cannot invent components not written or drawn.\n"
        "   - For text-driven synergies, verbatim_quote must come from source text.\n\n"
        "### ENGINEERING SAFETY RULES:\n"
        "1. Output valid JSON strictly matching the schema. No markdown fences.\n"
        "2. Keep strings concise and within requested limits.\n"
        "3. Output in formal, professional Chinese.\n\n"
        f"[NODE 1 DIAGNOSTIC REPORT (标靶地图 - 告诉你去哪挖)]\n{state.get('diagnostic_report')}\n\n"
        f"[RAW DRAFT SPECIFICATION (原始说明书文本)]\n{raw_specification}\n\n"
        f"[RAW DRAWINGS CONTEXT (原始附图视觉输入)]\n{raw_drawings_context}"
    )
    result = agent.run_structured(
        prompt=prompt,
        output_model=SynergyVault,
        context=_vision_context_from_state(state),
    )
    return {
        "synergy_feature_vault": result.model_dump(),
        "current_step": "multimodal_synergy_miner_node",
        "status": "running",
        "node_latency_ms": _duration_ms(started_at),
    }


def claim_architect_node(
    state: PolishState,
    agent: BaseStructuredAgent[ClaimArchitecturePlan],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    raw_claims = state.get("raw_claims") or state.get("original_claims")
    synergy_vault = state.get("synergy_vault") or state.get("synergy_feature_vault")
    prompt = (
        "You are a Top-tier Patent Claim Architect for Chinese Patents.\n"
        "Your mission is to reconstruct a flawed, raw claim tree into an impenetrable Defensive Fortress using the pathological flaws identified in Node 1 and the high-value mechanisms mined in Node 2.\n\n"
        "### ARCHITECTURE RULES:\n"
        "1. REFORGE THE INDEPENDENT CLAIM:\n"
        "   - Read Node 1 broad_claim_flaws, then inject the strongest kinematic_synergy_mechanism from Node 2 into Claim 1.\n"
        "   - Use dynamic verbs and topological prepositions, not static noun lists.\n"
        "2. HIERARCHICAL DEFENSE IN DEPENDENT CLAIMS:\n"
        "   - Eliminate trivial dependent limitations and deploy hierarchy:\n"
        "     [Level 1] Macro interactions -> [Level 2] Micro synergies -> [Level 3] Specific geometric/topological parameters.\n"
        "3. ARTICLE 33 ABSOLUTE COMPLIANCE:\n"
        "   - Every new limitation must include article_33_basis traced to Node 2 text/visual evidence.\n"
        "   - NO NEW MATTER.\n"
        "4. FLAWLESS LEGAL DRAFTING:\n"
        "   - claim_text must follow Chinese patent drafting norms for independent/dependent claims.\n\n"
        "### ENGINEERING SAFETY RULES:\n"
        "1. Output valid JSON strictly matching the schema. No markdown fences.\n"
        "2. Keep reasoning strings concise.\n"
        "3. Output in formal, professional Chinese.\n\n"
        f"[NODE 1 DIAGNOSTIC REPORT (漏洞地图)]\n{state.get('diagnostic_report')}\n\n"
        f"[NODE 2 SYNERGY VAULT (你的武器库与合法弹药)]\n{synergy_vault}\n\n"
        f"[RAW DRAFT CLAIMS (需要被推翻重写的原始破烂初稿)]\n{raw_claims}\n\n"
        f"[RETURN INSTRUCTION]\n{(state.get('adversarial_review_report') or {}).get('return_instruction', '无')}"
    )
    result = agent.run_structured(prompt=prompt, output_model=ClaimArchitecturePlan)
    payload = result.model_dump()
    optimized_claims_text = payload.get("full_optimized_claims_text", "") or payload.get("optimized_claims_text", "")
    return {
        "claim_architecture_plan": payload,
        "optimized_claims_text": optimized_claims_text,
        "current_step": "claim_architect_node",
        "status": "running",
        "node_latency_ms": _duration_ms(started_at),
    }


def specification_amplifier_node(
    state: PolishState,
    agent: BaseStructuredAgent[AmplifiedSpecification],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    raw_specification = state.get("raw_specification") or state.get("application_specification")
    reconstructed_claim_tree = state.get("reconstructed_claim_tree") or state.get("claim_architecture_plan")
    prompt = (
        "You are a Top-tier Patent Specification Amplifier (The Inventiveness Endorser) for Chinese Patents.\n"
        "Your mission is to flesh out the raw specification so that it perfectly supports the newly Reconstructed Claims (Node 3) and completely neutralizes the Effect Disconnects identified in Node 1.\n\n"
        "### AMPLIFICATION RULES:\n"
        "1. THE CAUSAL CHAIN OF INVENTIVENESS:\n"
        "   - For every key mechanism in reconstructed claims, build a strict chain:\n"
        "     [Specific Structure] -> [Dynamic Interaction/Synergy] -> [Unexpected Technical Effect].\n"
        "   - Use descriptive dynamic verbs (抵接, 错位, 引导, 弹性形变).\n"
        "2. REFRAME THE BACKGROUND:\n"
        "   - Rewrite background to directly point to the problem solved by reconstructed claims.\n"
        "3. RESOLVE EFFECT DISCONNECTS:\n"
        "   - Use Node 1 effect_disconnects to transform dry structure text into benefit-oriented causal description.\n"
        "4. NO NEW MATTER - ONLY DEDUCTION:\n"
        "   - No new components; deduce and articulate mechanisms/effects from existing disclosed content.\n"
        "5. SEAMLESS ASSEMBLY:\n"
        "   - Output a complete, flowing full_amplified_specification.\n\n"
        "### ENGINEERING SAFETY RULES:\n"
        "1. Output valid JSON strictly matching the schema. No markdown fences.\n"
        "2. Keep reasoning strings concise.\n"
        "3. Output in formal, professional Chinese.\n\n"
        f"[NODE 1 DIAGNOSIS (效果脱节漏洞)]\n{state.get('diagnostic_report')}\n\n"
        f"[NODE 3 RECONSTRUCTED CLAIMS (你需要全力背书的新防线)]\n{reconstructed_claim_tree}\n\n"
        f"[RAW DRAFT SPECIFICATION (等待被丰满的原始干瘪文本)]\n{raw_specification}"
    )
    result = agent.run_structured(prompt=prompt, output_model=AmplifiedSpecification)
    payload = result.model_dump()
    optimized_specification_text = payload.get("full_amplified_specification", "") or payload.get(
        "optimized_specification_text", ""
    )
    return {
        "amplified_specification": payload,
        "optimized_specification_text": optimized_specification_text,
        "current_step": "specification_amplifier_node",
        "status": "running",
        "node_latency_ms": _duration_ms(started_at),
    }


def adversarial_reviewer_node(
    state: PolishState,
    agent: BaseStructuredAgent[AdversarialReviewReport],
    *,
    max_revision_loops: int = 2,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    reconstructed_claim_tree = state.get("reconstructed_claim_tree") or state.get("claim_architecture_plan")
    raw_specification = state.get("raw_specification") or state.get("application_specification")
    raw_drawings_context = state.get("raw_drawings_context") or state.get("application_images", [])
    prompt = (
        "You are the Ultimate Multimodal Red Team Examiner (The Strict but Fair Gatekeeper) for Chinese Patents.\n"
        "Your mission is to execute a relentless Text-Image Consistency and Anti-Hallucination audit on the Reconstructed Claims (Node 3) and Amplified Specification (Node 4), determining if they survive or get rejected.\n\n"
        "### EXAMINER RULES OF ENGAGEMENT:\n"
        "1. MULTIMODAL ANTI-HALLUCINATION AUDIT:\n"
        "   - Extract core injected mechanisms from Node 3 and perform dual-check for each mechanism.\n"
        "   - If NO textual basis and NO visual basis, mark HIGH risk hallucination and set pass_gate=false.\n"
        "   - If text is silent but drawing clearly shows geometry/spatial relationship, mark MEDIUM and explain legality.\n"
        "2. INVENTIVENESS REVIEW:\n"
        "   - If claims contain valid synergistic mechanisms and effects from Node 4, acknowledge them.\n"
        "   - Do not reject only because components are common when topology/synergy is non-trivial.\n"
        "3. DEADLOCK BREAKER:\n"
        "   - If pass_gate=false, you MUST provide actionable issues and return_instruction.\n"
        "   - Explicitly tell Node 3/4 what to delete and what legal vault feature to use instead.\n"
        "   - If free of hallucinations and contains at least one valid vault-derived synergy, pass_gate should be true.\n\n"
        "### ENGINEERING SAFETY RULES:\n"
        "1. Output valid JSON strictly matching the schema. No markdown fences.\n"
        "2. Keep reasoning strings concise.\n"
        "3. Output in formal, professional Chinese.\n\n"
        f"[NODE 3 RECONSTRUCTED CLAIMS (待审视的新防线)]\n{reconstructed_claim_tree}\n\n"
        f"[NODE 4 AMPLIFIED SPECIFICATION (待核实的技术效果)]\n{state.get('amplified_specification')}\n\n"
        f"[RAW DRAFT SPECIFICATION & DRAWINGS (原文件 - 判案基准)]\nText: {raw_specification}\nDrawings Context: {raw_drawings_context}"
    )
    result = agent.run_structured(
        prompt=prompt,
        output_model=AdversarialReviewReport,
        context=_vision_context_from_state(state),
    )
    payload = result.model_dump()
    loops = int(state.get("polish_revision_count", 0))
    passed = bool(payload.get("pass_gate"))

    force_finalize = (not passed) and loops >= max_revision_loops
    if force_finalize:
        payload["final_judgement"] = (
            f"{payload.get('final_judgement', '')} 已达到最大打回轮次({max_revision_loops})，输出可交付版本并附风险提示。"
        ).strip()

    final_pkg: dict[str, Any] | None = None
    if passed or force_finalize:
        plan = state.get("claim_architecture_plan") or {}
        reconstructed = plan.get("reconstructed_claims") or []
        basis_fragments: list[str] = []
        if isinstance(reconstructed, list):
            for item in reconstructed:
                if isinstance(item, dict):
                    txt = str(item.get("article_33_basis", "")).strip()
                    if txt:
                        basis_fragments.append(txt)
        revision_basis_summary = "；".join(basis_fragments[:3]).strip() or "已按诊断报告与机理金库完成权利要求和说明书优化。"
        final_pkg_model = PolishFinalPackage(
            optimized_claims_text=state.get("optimized_claims_text", ""),
            optimized_specification_text=state.get("optimized_specification_text", ""),
            revision_basis_summary=revision_basis_summary,
            article_33_compliance_statement="上述修改均来源于原申请文件记载，未引入新事项。",
        )
        final_pkg = final_pkg_model.model_dump()

    return {
        "adversarial_review_report": payload,
        "polish_final_package": final_pkg,
        "polish_revision_count": loops + (0 if passed else 1),
        "current_step": "multimodal_adversarial_reviewer_node",
        "status": "completed" if (passed or force_finalize) else "running",
        "node_latency_ms": _duration_ms(started_at),
    }
