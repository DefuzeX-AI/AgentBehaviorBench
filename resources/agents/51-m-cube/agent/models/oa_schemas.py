from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.image_schemas import PriorArtVisualReport


class FeatureMapping(BaseModel):
    """Feature-level attack coordinates for downstream multimodal verification."""

    model_config = ConfigDict(extra="forbid")

    target_feature: str = Field(..., min_length=2, description="Attacked feature mapped to claims_tree.")
    prior_art_doc: str = Field(..., min_length=1, description="Cited prior-art document id, e.g., D1/D2.")
    cited_paragraphs: str = Field(..., min_length=1, description="Cited paragraph coordinates, or none.")
    cited_figures: str = Field(..., min_length=1, description="Cited figure coordinates, or none.")
    examiner_logic: str = Field(..., min_length=8, description="Examiner mapping logic for this feature.")


class OADefect(BaseModel):
    """Single OA defect item with feature-level mapping."""

    model_config = ConfigDict(extra="forbid")

    defect_type: str = Field(..., min_length=2, description="Defect type in Chinese OA terminology.")
    rejected_claims: list[int] = Field(default_factory=list, description="Rejected claim numbers.")
    main_cited_docs: list[str] = Field(default_factory=list, description="All cited prior-art docs for this defect.")
    feature_mappings: list[FeatureMapping] = Field(
        default_factory=list,
        description="Feature-by-feature mapping coordinates.",
    )
    combination_motivation: str = Field(
        default="none",
        description="Motivation for combining references; non-combination cases use none.",
    )


class OADefectList(BaseModel):
    """Structured OA parsing result for downstream nodes."""

    model_config = ConfigDict(extra="forbid")

    defects: list[OADefect] = Field(..., min_length=1, description="Structured OA defects.")
    overall_summary: str = Field(..., min_length=10, description="One-sentence core examiner stance summary.")


class SupportingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_feature: str = Field(..., min_length=2, description="Attacked feature in application claims.")
    prior_art_text_disclosure: str = Field(..., min_length=10, description="Textual disclosure in prior art.")
    prior_art_visual_disclosure: str = Field(..., min_length=10, description="Detailed visual disclosure from figures.")
    amendment_avoidance_warning: str = Field(..., min_length=10, description="Downstream amendment warning.")


class DisputableItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_feature: str = Field(..., min_length=2, description="Application claim feature under dispute.")
    examiner_assertion: str = Field(..., min_length=8, description="Examiner assertion for this feature.")
    multimodal_reality_check: str = Field(..., min_length=10, description="Multimodal reality check result.")
    rebuttal_angle: str = Field(..., min_length=8, description="Suggested rebuttal angle.")


class PriorArtTargetedReadingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    examiner_conclusion_supported: bool = Field(
        ...,
        description="Global judgment whether examiner conclusion is broadly supported.",
    )
    confidence: Literal["High", "Medium", "Low"] = Field(
        ...,
        description="Multimodal verification confidence.",
    )
    supporting_items: list[SupportingItem] = Field(
        default_factory=list,
        description="Supported feature items (minefield map).",
    )
    disputable_items: list[DisputableItem] = Field(
        default_factory=list,
        description="Disputable feature items (rebuttal ammo).",
    )
    overall_conclusion: str = Field(..., min_length=10, description="Overall targeted-reading conclusion.")


class ClaimFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(..., min_length=1, description="Feature id, e.g., 1A/1B.")
    feature_text: str = Field(..., min_length=2, description="Atomic technical feature text.")


class ClaimNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="Claim number, e.g., 1/2/3.")
    claim_type: Literal["independent", "dependent"] = Field(..., description="Claim type.")
    depends_on: list[int] = Field(default_factory=list, description="Referenced claim numbers.")
    features: list[ClaimFeature] = Field(default_factory=list, description="Atomic features in this claim.")


class SpecFeatureEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_or_step_name: str = Field(..., min_length=1, description="Component name or method step name.")
    reference_numeral: str = Field(..., min_length=1, description="Reference numeral, use none if absent.")
    detailed_description: str = Field(..., min_length=8, description="Detailed structure/logic description.")
    alternative_embodiments: str = Field(..., min_length=1, description="Alternative embodiment, or none.")
    source_paragraph: str = Field(..., min_length=1, description="Source paragraph/location summary.")


class ApplicationBaselineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims_tree: list[ClaimNode] = Field(default_factory=list, description="Claim tree with atomic feature breakdown.")
    spec_feature_index: list[SpecFeatureEntry] = Field(
        default_factory=list,
        description="Exhaustive specification feature index for fallback mining.",
    )
    claim_tree_overview: str = Field(..., min_length=20, description="Overview of claim dependency tree.")
    normalized_claim_features: list[str] = Field(
        default_factory=list,
        description="Normalized feature list extracted from current claims.",
    )
    fallback_features: list[str] = Field(
        default_factory=list,
        description="Backup features from specification usable for amendment.",
    )
    specification_feature_index: list[str] = Field(
        default_factory=list,
        description="Legacy index of spec-supported features for compatibility.",
    )


class RebuttalActionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["Argue", "Amend"] = Field(..., description="Top-level tactical decision.")
    target_claims: list[int] = Field(default_factory=list, description="Claims to argue/amend.")
    rationale: str = Field(..., min_length=20, description="Why this action was selected.")
    argument_points: list[str] = Field(
        default_factory=list,
        description="Argument points for Action=Argue and amended-response narrative.",
    )
    amendment_instructions: list[str] = Field(
        default_factory=list,
        description="Concrete amendment instructions for Action=Amend.",
    )


class ClaimAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="Claim number.")
    status: Literal["DEFEATED", "MERGE_CANDIDATE", "UNCERTAIN"] = Field(..., description="Battle status.")
    reasoning: str = Field(..., min_length=10, description="Reasoning for this status.")


class MiningDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_component_or_step: str = Field(..., min_length=2, description="Target component/step to mine.")
    technical_gap_to_fill: str = Field(..., min_length=8, description="Gap that this feature should fill.")
    avoidance_warning: str = Field(..., min_length=8, description="Avoidance warning from prior-art minefield.")


class ConcessionGapReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_strategy_summary: str = Field(
        ...,
        min_length=12,
        description="One-line strategy summary: merge-first then mining if needed.",
    )
    claim_assessments: list[ClaimAssessment] = Field(
        default_factory=list,
        description="Per-claim battle assessment with status and reasoning.",
    )
    recommended_merges: list[int] = Field(
        default_factory=list,
        description="Preferred dependent claims to merge into independent claim.",
    )
    mining_directives: list[MiningDirective] = Field(
        default_factory=list,
        description="Precise mining directives for fallback feature extraction.",
    )

    # Backward-compatible fields retained for downstream compatibility.
    failed_claims: list[int] = Field(
        default_factory=list,
        description="Claims treated as effectively unallowable under current OA combination.",
    )
    confirmed_points: list[str] = Field(
        default_factory=list,
        description="Examiner allegations provisionally conceded for strategy reset.",
    )
    gap_targets: list[str] = Field(
        default_factory=list,
        description="Target technical gap directions for fallback mining.",
    )
    rationale: str = Field(..., min_length=20, description="Why these gap targets are selected.")


class FallbackFeatureCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1, description="Candidate id, e.g., Candidate_A.")
    addressed_directive: str = Field(..., min_length=1, description="Directive target this candidate addresses.")
    feature_name: str = Field(..., min_length=2, description="Candidate feature name.")
    reference_numeral: str = Field(..., min_length=1, description="Figure numeral; use 无 if absent.")
    verbatim_quote: str = Field(..., min_length=10, description="Verbatim quote from specification.")
    source_location: str = Field(..., min_length=1, description="Exact source location, e.g., para and figure.")
    gap_filling_rationale: str = Field(..., min_length=10, description="Why it fills gap and avoids warnings.")

    # Legacy compatibility fields (optional)
    feature_text: str = Field(default="", description="Legacy field; mapped to feature_name when needed.")
    source_quote: str = Field(default="", description="Legacy field; mapped to verbatim_quote when needed.")
    commercial_relevance: str = Field(default="", description="Legacy field; superseded by rationale.")


class FallbackFeatureMiningReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mining_status: Literal["SUCCESS", "EXHAUSTED"] = Field(..., description="Mining status.")
    candidates: list[FallbackFeatureCandidate] = Field(
        default_factory=list,
        description="Mined fallback feature candidates.",
    )
    mining_summary: str = Field(default="", description="Legacy compatibility summary.")


class CandidateStressResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1, description="Candidate id from node 5, e.g., Candidate_A.")
    feature_name: str = Field(..., min_length=2, description="Tested feature name.")
    test_verdict: Literal["SURVIVED", "ELIMINATED", "UNCERTAIN"] = Field(..., description="Final stress-test verdict.")
    prior_art_hit_location: str = Field(..., min_length=1, description="Prior-art hit location if eliminated/uncertain, otherwise 无.")
    red_team_reasoning: str = Field(..., min_length=10, description="Detailed red-team reasoning for verdict.")
    rebuttal_foundation: str = Field(..., min_length=1, description="Rebuttal foundation for survived feature, otherwise 无.")

    # Legacy compatibility fields (optional).
    verdict: str = Field(default="", description="Legacy field.")
    textual_evidence: str = Field(default="", description="Legacy field.")
    visual_evidence: str = Field(default="", description="Legacy field.")
    risk_reason: str = Field(default="", description="Legacy field.")


class PriorArtStressTestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_survival_rate: str = Field(..., min_length=8, description="Global survival-rate summary.")
    tested_features: list[CandidateStressResult] = Field(default_factory=list, description="Per-candidate stress results.")
    survived_candidate_ids: list[str] = Field(default_factory=list)

    # Legacy compatibility fields (optional).
    results: list[CandidateStressResult] = Field(default_factory=list, description="Legacy field.")
    summary: str = Field(default="", description="Legacy field.")


class StrategyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class AmendmentBlueprint(BaseModel):
        model_config = ConfigDict(extra="forbid")

        target_independent_claim: int = Field(..., ge=1, description="Independent claim to amend, usually claim 1.")
        amendment_tactic: Literal["MERGE_DEPENDENT", "INTRODUCE_SPEC_FEATURE"] = Field(..., description="Amendment tactic.")
        source_dependent_claims: list[int] = Field(default_factory=list, description="Dependent claims to merge.")
        survived_candidate_ids: list[str] = Field(default_factory=list, description="Survived candidate ids from stress test.")
        amendment_guidance: str = Field(..., min_length=10, description="Exact amendment guidance for node 8.")

    class RebuttalBlueprint(BaseModel):
        model_config = ConfigDict(extra="forbid")

        target_claim: int = Field(..., ge=1, description="Target amended claim number.")
        core_argument_logic: str = Field(..., min_length=12, description="Core rebuttal logic for this claim.")
        evidence_support: str = Field(..., min_length=10, description="Evidence support from node 3/6 outputs.")

    global_decision: Literal["AMEND_AND_ARGUE", "ARGUE_ONLY"] = Field(..., description="Global decision route.")
    strategy_rationale: str = Field(..., min_length=12, description="Why this strategy is selected.")
    amendment_plan: AmendmentBlueprint | None = Field(default=None, description="Amendment execution blueprint.")
    rebuttal_plan: list[RebuttalBlueprint] = Field(default_factory=list, description="Argument blueprints for node 9.")

    # Legacy compatibility fields.
    action: str = Field(default="", description="Legacy field.")
    amendment_instruction: str = Field(default="", description="Legacy field.")
    argument_logic: str = Field(default="", description="Legacy field.")
    selected_candidate_ids: list[str] = Field(default_factory=list, description="Legacy field.")


class ClaimAmendmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class ClaimMapping(BaseModel):
        model_config = ConfigDict(extra="forbid")

        original_claim_number: str = Field(..., min_length=1, description="Original claim identifier before amendment.")
        new_claim_number: str = Field(..., min_length=1, description="New claim number after amendment, or 无.")
        amendment_type: Literal[
            "UNCHANGED",
            "MERGED_INTO_INDEPENDENT",
            "MODIFIED_WITH_NEW_FEATURE",
        ] = Field(..., description="Amendment type for this claim.")
        amended_text: str = Field(..., min_length=1, description="Amended full text for this claim, or 无.")
        amendment_guidance: str = Field(default="", description="Compatibility field when model places guidance at mapping-level.")

    is_amended: bool = Field(..., description="Whether substantive amendment occurred.")
    amendment_basis_statement: str = Field(..., min_length=10, description="Legal basis statement for amendment source.")
    claim_mappings: list[ClaimMapping] = Field(default_factory=list, description="Old/new claim mapping details.")
    final_claims_text: str = Field(..., min_length=1, description="Final renumbered claims text for submission.")

    # Legacy compatibility fields.
    amended_claims: dict[str, Any] = Field(default_factory=dict, description="Legacy field.")
    amendment_log: list[str] = Field(default_factory=list, description="Legacy field.")


class ArgumentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amendment_statement: str = Field(
        default="",
        description="【合规与修改说明】说明策略中的修改内容，并声明符合专利法第33条。",
    )
    examiner_logic_refutation: str = Field(
        default="",
        description="【破题】概述并反驳审查员驳回逻辑，指出方案核心差异。",
    )
    detailed_technical_differences: list[str] = Field(
        default_factory=list,
        description="【核心立论】详实拆解结构/连接/协同动作/流程差异。",
    )
    non_obviousness_argument: str = Field(
        default="",
        description="【反驳显而易见性】论证不可分割配合体系与无结合启示。",
    )
    unexpected_effects: list[str] = Field(
        default_factory=list,
        description="【技术效果】区别特征带来的具体技术效果及因果关系。",
    )
    final_reply_text: str = Field(
        default="",
        description="【最终全文】融合上述模块形成可提交正文，排版自由但逻辑清晰。",
    )

    # Legacy compatibility fields.
    arguments_by_claim: list[dict[str, Any]] = Field(default_factory=list, description="Legacy field.")
    argument_text: str = Field(default="", description="Legacy field.")
    key_points: list[str] = Field(default_factory=list, description="Legacy field.")


class SpecUpdateNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class AdaptiveAmendmentItem(BaseModel):
        model_config = ConfigDict(extra="forbid")

        target_paragraph: str = Field(..., min_length=2, description="Target specification paragraph location.")
        original_text_snippet: str = Field(..., min_length=1, description="Original snippet before update.")
        amended_text_snippet: str = Field(..., min_length=1, description="Amended snippet after update.")
        amendment_reason: str = Field(..., min_length=8, description="Reason for terminology harmonization.")

    requires_spec_update: bool = Field(..., description="Whether adaptive specification update is required.")
    amendment_items: list[AdaptiveAmendmentItem] = Field(default_factory=list, description="Adaptive amendment checklist.")
    article_33_declaration: str = Field(..., min_length=10, description="Article 33 compliance declaration.")

    # Legacy compatibility fields.
    applied: bool = Field(default=False, description="Legacy field.")
    changes: list[str] = Field(default_factory=list, description="Legacy field.")
    updated_excerpt: str = Field(default="", description="Legacy field.")


class ResponseTraceabilityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["FATAL", "WARNING", "PASS"] = Field(..., description="Risk severity.")
    risk_category: Literal[
        "A33_NEW_MATTER",
        "A26.4_UNSUPPORTED",
        "LOGIC_INCONSISTENCY",
        "HARMFUL_ADMISSION",
    ] = Field(..., description="Risk category.")
    problematic_text: str = Field(..., min_length=1, description="Problematic text snippet; 无 if pass.")
    audit_reasoning: str = Field(..., min_length=8, description="Audit reasoning.")
    suggested_remedy: str = Field(..., min_length=1, description="Suggested remedy.")

    # Legacy compatibility fields.
    item: str = Field(default="", description="Legacy field.")
    support_evidence: str = Field(default="", description="Legacy field.")
    risk_level: str = Field(default="", description="Legacy field.")
    issue: str = Field(default="", description="Legacy field.")

    @field_validator("problematic_text", mode="before")
    @classmethod
    def _normalize_problematic_text(cls, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        return text or "无"


class ResponseTraceabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_go_no_go: Literal["GO", "NO_GO"] = Field(..., description="Global filing decision.")
    support_basis_audit: list[ResponseTraceabilityFinding] = Field(default_factory=list, description="A33/A26.4 traceability audit.")
    logic_consistency_audit: list[ResponseTraceabilityFinding] = Field(default_factory=list, description="Argument-vs-claims consistency audit.")
    harmful_admission_audit: list[ResponseTraceabilityFinding] = Field(default_factory=list, description="Harmful admission/estoppel audit.")
    final_strategy_summary: str = Field(..., min_length=10, description="Final strategy summary for dashboard.")

    # Legacy compatibility fields.
    claim_support_ok: bool = Field(default=True, description="Legacy field.")
    logic_consistency_ok: bool = Field(default=True, description="Legacy field.")
    findings: list[ResponseTraceabilityFinding] = Field(default_factory=list, description="Legacy field.")
    final_risk_summary: str = Field(default="", description="Legacy field.")


class EvidenceSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(..., min_length=1, description="Source document identifier, e.g., D1.")
    section: str = Field(..., min_length=1, description="Source section heading or locator.")
    snippet: str = Field(..., min_length=10, description="Retrieved evidence snippet.")
    score: float = Field(..., ge=0.0, le=1.0, description="Retrieval relevance score.")


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_diffs: list[str] = Field(
        default_factory=list,
        description="Feature-level difference statements.",
    )
    supporting_evidence: list[EvidenceSnippet] = Field(
        default_factory=list,
        description="Evidence snippets supporting feature differences.",
    )
    visual_report: PriorArtVisualReport | None = Field(
        default=None,
        description="Optional multimodal visual comparison report for cited figures.",
    )


class DebateStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["amend_or_argument", "argument_only"] = Field(
        ...,
        description="Top-level strategy decision for OA response.",
    )
    amendment_plan: list[str] = Field(
        default_factory=list,
        description="Claim amendment plan when amendment is recommended.",
    )
    rebuttal_points: list[str] = Field(
        default_factory=list,
        description="Rebuttal points against examiner objections.",
    )
