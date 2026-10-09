from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class BroadClaimFlaw(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="有缺陷的权利要求编号")
    flaw_description: str = Field(..., min_length=1, description="缺陷描述")
    missing_topological_constraint: str = Field(
        ...,
        min_length=1,
        description="建议引入的拓扑约束或动作逻辑（给节点3）",
    )


class DependentClaimFault(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="有缺陷的从属权利要求编号")
    trivial_limitation: str = Field(..., min_length=1, description="无效限定点")
    upgrade_direction: str = Field(..., min_length=1, description="建议升级方向（给节点3）")


class EffectDisconnect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_location: str = Field(..., min_length=1, description="缺陷所在段落或位置")
    dry_structure_mentioned: str = Field(..., min_length=1, description="干瘪结构描述原文")
    missing_technical_effect: str = Field(..., min_length=1, description="漏写的技术效果/技术问题（给节点4）")


class TextVisualMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figure_label: str = Field(..., min_length=1, description="存在隐式机理的附图编号")
    text_omission_description: str = Field(..., min_length=1, description="文本遗漏点")
    visual_goldmine_evidence: str = Field(..., min_length=1, description="图上明确但文本未写的关键视觉证据")


class DiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_diagnosis_summary: str = Field(..., min_length=1, description="全案整体诊断摘要")
    broad_claim_flaws: list[BroadClaimFlaw] = Field(default_factory=list, description="宽泛黑洞清单")
    dependent_claim_faults: list[DependentClaimFault] = Field(default_factory=list, description="从权断层清单")
    effect_disconnects: list[EffectDisconnect] = Field(default_factory=list, description="效果脱节清单")
    text_visual_mismatches: list[TextVisualMismatch] = Field(default_factory=list, description="图文一致性缺陷清单")


class SynergyGold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=1, description="机理特征名称")
    source_paragraph: str = Field(..., min_length=1, description="文本出处，如说明书段落号；纯看图则写无明确文字记载")
    verbatim_quote: str = Field(..., min_length=1, description="原话摘抄；纯看图发现可填无")
    source_figure: str = Field(..., min_length=1, description="视觉出处，如图2或图3剖视图")
    visual_morphology: str = Field(..., min_length=1, description="视觉几何形态与相对位置")
    kinematic_synergy_mechanism: str = Field(..., min_length=1, description="动态装配与协同逻辑")
    derived_technical_effect: str = Field(..., min_length=1, description="推演出的技术效果")


class SynergyVault(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_summary: str = Field(..., min_length=1, description="整体机理价值评估")
    text_driven_synergies: list[SynergyGold] = Field(default_factory=list, description="文字深挖区机理特征")
    visual_driven_synergies: list[SynergyGold] = Field(default_factory=list, description="视觉淘金区机理特征")


class SynergyFeatureVault(SynergyVault):
    """Backward-compatible alias for existing workflow type hints."""


class ReconstructedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="重构后的权利要求编号")
    dependencies: list[int] = Field(default_factory=list, description="引用权利要求编号列表，主权填 []")
    injected_synergy_mechanism: str = Field(..., min_length=1, description="注入的协同机理与对应修复缺陷")
    article_33_basis: str = Field(..., min_length=1, description="新增机理在原申请中的出处依据")
    inventiveness_defense: str = Field(..., min_length=1, description="针对显而易见性质疑的反驳要点")
    claim_text: str = Field(..., min_length=1, description="规范法言法语的完整权利要求文本")


class ClaimTreeArchitecture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    independent_claim_strategy: str = Field(..., min_length=1, description="主权破局战略")
    dependent_claim_hierarchy: str = Field(..., min_length=1, description="从权纵深排兵布阵逻辑")
    reconstructed_claims: list[ReconstructedClaim] = Field(default_factory=list, description="重构后的完整权利要求树")
    full_optimized_claims_text: str = Field(..., min_length=1, description="完整《权利要求书》纯文本")


class ClaimArchitecturePlan(ClaimTreeArchitecture):
    """Backward-compatible alias for existing workflow type hints."""

    # Compatibility field for legacy consumers/tests that expect a top-level
    # article_33_basis summary (new schema keeps per-claim article_33_basis).
    article_33_basis: str = Field(
        default="未提供",
        min_length=1,
        description="兼容字段：修改依据（专利法第33条）总体说明",
    )


class AmplifiedParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_claim_number: int = Field(..., ge=1, description="该段落主要支撑的权利要求编号")
    core_mechanism: str = Field(..., min_length=1, description="核心结构或协同机理")
    dynamic_action_description: str = Field(..., min_length=1, description="动作与机理推演")
    unexpected_technical_effect: str = Field(..., min_length=1, description="预料不到的技术效果")
    injected_text_snippet: str = Field(..., min_length=1, description="可直接插入的说明书正文段落")


class SpecificationAmplificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    background_problem_reframing: str = Field(..., min_length=1, description="重构后的背景技术问题引导")
    amplified_paragraphs: list[AmplifiedParagraph] = Field(default_factory=list, description="逐条权利要求的扩写段落")
    full_amplified_specification: str = Field(..., min_length=1, description="融合后的完整说明书全文")


class AmplifiedSpecification(SpecificationAmplificationReport):
    """Backward-compatible alias for existing workflow type hints."""


class AntiHallucinationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    injected_mechanism: str = Field(..., min_length=1, description="新增核心协同机理或结构特征")
    textual_basis_found: bool = Field(..., description="文本中是否有记载")
    visual_basis_found: bool = Field(..., description="附图中是否有对应形态或动作逻辑")
    hallucination_risk_level: Literal["LOW", "MEDIUM", "HIGH"] = Field(..., description="幻觉风险定级")
    audit_reasoning: str = Field(..., min_length=1, description="图文对账理由说明")


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_type: Literal["HALLUCINATION", "INVENTIVENESS_LACKING", "EFFECT_DISCONNECT"] = Field(
        ...,
        description="缺陷类型",
    )
    description: str = Field(..., min_length=1, description="缺陷表现")
    fix_suggestion: str = Field(
        ...,
        validation_alias=AliasChoices("fix_suggestion", "counter_strategy"),
        min_length=1,
        description="建设性修复建议",
    )


class AdversarialReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anti_hallucination_findings: list[AntiHallucinationCheck] = Field(default_factory=list, description="反幻觉图文对账清单")
    issues: list[ReviewIssue] = Field(default_factory=list, description="缺陷清单，若通过可为空")
    pass_gate: bool = Field(..., description="是否通过红蓝对抗终审")
    return_instruction: str = Field(default="通过，无需打回。", min_length=1, description="未通过时给节点3的打回指令")
    final_judgement: str = Field(..., min_length=1, description="最终判断说明")


class PolishFinalPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optimized_claims_text: str = Field(..., min_length=1, description="优化后权利要求全文")
    optimized_specification_text: str = Field(..., min_length=1, description="优化后说明书全文")
    revision_basis_summary: str = Field(..., min_length=1, description="修改依据摘要")
    article_33_compliance_statement: str = Field(..., min_length=1, description="第33条合规声明")
