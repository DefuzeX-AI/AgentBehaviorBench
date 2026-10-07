from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TechFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=2, description="具体的技术特征或部件名称。")
    detailed_structure_or_step: str = Field(
        ...,
        min_length=20,
        description="该特征的详细结构关系、参数约束或执行步骤（尽可能详尽）。",
    )
    solved_sub_problem: str = Field(..., min_length=10, description="该具体特征对应解决的子问题。")
    specific_effect: str = Field(..., min_length=10, description="该特征带来的直接有益效果及其作用机理。")


class TechSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_quotes: list[str] = Field(..., min_length=1, description="逐字摘抄交底书中关于痛点、方案与效果的关键原话片段。")
    background_and_core_problems: list[str] = Field(..., min_length=3, description="现有技术缺陷与待解决问题，至少列出3点。")
    core_solution_overview: str = Field(..., min_length=40, description="对整体技术方案核心发明点的详细概述。")
    detailed_features: list[TechFeature] = Field(..., min_length=3, description="穷尽式拆解交底书中的技术特征、部件、步骤及其逻辑关系。")
    overall_advantages: list[str] = Field(..., min_length=3, description="发明带来的全局有益效果，至少列出3点。")


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="权利要求编号，如1,2,3。")
    claim_type: str = Field(..., description="权利要求类型：independent 或 dependent。")
    depends_on: list[int] = Field(default_factory=list, description="引用的目标权利要求编号列表；独立权利要求为空。")
    preamble: str = Field(..., min_length=4, description="主题名称（前序部分）。")
    transition: str = Field(..., min_length=2, description="过渡词，通常为：包括：或其特征在于：")
    elements: list[str] = Field(..., min_length=1, description="技术特征列表，需拆分为多个独立特征段落。")
    full_text: str = Field(..., min_length=20, description="由preamble+transition+elements拼接的完整权利要求单句。")


class ClaimsSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[Claim] = Field(..., min_length=1, description="权利要求列表，必须以编号1的独立权利要求开始。")


class ClaimRevision(BaseModel):
    """Lenient claim schema used only for revise_claims_node output parsing."""

    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1)
    claim_type: str = Field(default="dependent")
    depends_on: list[int] = Field(default_factory=list)
    preamble: str = Field(default="")
    transition: str = Field(default="")
    elements: list[str] = Field(default_factory=list)
    full_text: str = Field(default="")


class ClaimsSetRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimRevision] = Field(..., min_length=1)


class EvidenceSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_text: str = Field(..., min_length=4, description="权利要求中拆解出的一个独立技术特征。")
    verbatim_quote: str = Field(..., min_length=4, description="交底书原文中支持该特征的原话摘抄。")
    support_level: str = Field(..., description="支持力度：Explicit / Implicit / Unsupported。")
    reasoning: str = Field(..., min_length=8, description="解释该摘抄为何支持该特征；若隐式或不支持需说明逻辑。")


class ClaimTraceability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="被核对的权利要求编号。")
    elements_evidence: list[EvidenceSnippet] = Field(..., min_length=1, description="该项权利要求中所有技术特征的溯源证据列表。")
    is_fully_supported: bool = Field(..., description="该项权利要求的所有特征是否都获得足够支持。")


class ClaimTraceabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: list[ClaimTraceability] = Field(..., min_length=1, description="所有权利要求的溯源审查报告。")
    overall_risk_assessment: str = Field(..., min_length=20, description="全局风险评估：总结超范围风险与人工审查建议。")


class InventionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_problem: str = Field(..., min_length=30, description="要解决的技术问题。")
    technical_solution: str = Field(..., min_length=100, description="技术方案，需全面覆盖权利要求内容。")
    beneficial_effects: str = Field(..., min_length=50, description="有益效果，需详细论述特征带来的效果。")


class ComponentDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., description="核心部件名称或方法步骤名称（可带附图标记）。")
    structure_and_connection: str = Field(..., min_length=30, description="该部件结构或步骤逻辑，以及与其他部件的连接关系。")
    working_principle: str = Field(..., min_length=30, description="该部件/步骤在整体方案中的作用和原理。")


class DetailedImplementation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    introductory_boilerplate: str = Field(..., description="标准套话开头。")
    overall_architecture: str = Field(..., min_length=100, description="结合附图的整体架构与流程介绍。")
    component_details: list[ComponentDetail] = Field(..., min_length=1, description="核心技术特征逐一拆解描述。")
    workflow_description: str = Field(..., min_length=100, description="系统运行或方法执行的完整流程。")
    alternative_embodiments: str = Field(..., min_length=50, description="常规替代方案补充。")


class Specification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=2, description="发明名称。")
    technical_field: str = Field(..., min_length=20, description="技术领域。")
    background_art: str = Field(..., min_length=100, description="背景技术。")
    invention_content: InventionContent = Field(..., description="发明内容（三段式：问题、方案、效果）。")
    drawings_description: str = Field(..., min_length=10, description="附图说明。")
    detailed_implementation: DetailedImplementation = Field(..., description="具体实施方式拆解模块。")
