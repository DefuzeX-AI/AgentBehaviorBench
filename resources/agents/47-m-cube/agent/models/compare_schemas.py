from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class MultimodalAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_numeral: str = Field(default="无", min_length=1, description="附图标记（如10/404），无则填“无”")
    figure_labels: list[str] = Field(default_factory=list, description="出现该特征的附图编号，例如 ['图1','图3']")
    visual_morphology: str = Field(
        default="未提供视觉形态描述，建议人工核对。",
        min_length=1,
        description="结合说明书与附图的形态/位置/连接关系描述",
    )

    @field_validator("reference_numeral", "visual_morphology", mode="before")
    @classmethod
    def _fill_anchor_text(cls, value: object, info) -> str:
        defaults = {
            "reference_numeral": "无",
            "visual_morphology": "未提供视觉形态描述，建议人工核对。",
        }
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        return defaults.get(info.field_name, "无")


class AtomicFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(..., min_length=1, description="特征唯一编号，例如 F1.1")
    verbatim_text: str = Field(..., min_length=2, description="权利要求原话摘抄")
    entity_components: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("entity_components", "parsed_components"),
        description="名词级实体部件列表",
    )
    connection_and_synergy: str = Field(
        default="未提取到明确连接关系，建议人工复核原文。",
        min_length=1,
        description="部件间连接关系与协同机理",
    )
    visual_anchor: MultimodalAnchor = Field(default_factory=MultimodalAnchor, description="该特征的视觉锚点")

    @field_validator("connection_and_synergy", mode="before")
    @classmethod
    def _fill_atomic_synergy(cls, value: object) -> str:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        return "未提取到明确连接关系，建议人工复核原文。"


class ClaimNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="权利要求编号")
    is_independent: bool = Field(..., description="是否为独立权利要求")
    dependency: list[int] = Field(default_factory=list, description="引用权利要求编号，独立权利要求填 []")
    atomic_features: list[AtomicFeature] = Field(default_factory=list, description="原子级技术特征列表")


class FallbackFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=1, description="后备特征名称")
    verbatim_quote: str = Field(..., min_length=2, description="说明书原话摘抄")
    connection_and_synergy: str = Field(
        default="未提取到明确协同机理，建议人工复核。",
        validation_alias=AliasChoices("connection_and_synergy", "detailed_description"),
        min_length=1,
        description="后备特征的连接结构或工作机理",
    )
    source_location: str = Field(default="未标注具体段落/图号", min_length=1, description="出处段落或图号")
    visual_anchor: MultimodalAnchor = Field(default_factory=MultimodalAnchor, description="后备特征视觉锚点")

    @field_validator("connection_and_synergy", mode="before")
    @classmethod
    def _fill_fallback_synergy(cls, value: object) -> str:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        return "未提取到明确协同机理，建议人工复核。"


class DraftBaselineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims_tree: list[ClaimNode] = Field(default_factory=list, description="解析后的权利要求依赖树及原子特征")
    fallback_feature_index: list[FallbackFeature] = Field(
        default_factory=list,
        validation_alias=AliasChoices("fallback_feature_index", "spec_feature_index"),
        description="说明书后备特征库（兼容旧字段 spec_feature_index）",
    )


class PriorArtComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_name: str = Field(..., min_length=1, description="部件名称")
    reference_numeral: str = Field(default="无", min_length=1, description="附图标记，无则填“无”")
    structural_connections_and_mechanisms: str = Field(
        ...,
        validation_alias=AliasChoices("structural_connections_and_mechanisms", "text_disclosure"),
        min_length=1,
        description="文字线中的装配连接与协同机理（含段落号）",
    )
    visual_appearance: str = Field(..., min_length=1, description="该部件在附图中的视觉形态")


class FigureConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_component: str = Field(..., min_length=1, description="起始部件（带标记）")
    target_component: str = Field(..., min_length=1, description="目标部件（带标记）")
    kinematic_relationship: str = Field(
        ...,
        validation_alias=AliasChoices("kinematic_relationship", "connection_type"),
        min_length=1,
        description="视觉连接与运动状态关系",
    )


class FigureLibrary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figure_label: str = Field(..., min_length=1, description="附图编号")
    observed_components: list[str] = Field(default_factory=list, description="图中可见部件标记")
    visual_connections: list[FigureConnection] = Field(default_factory=list, description="图中部件连接关系")


class TargetedReadingAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_image_count: int = Field(..., ge=0, description="传入附图总数")
    actually_used_image_count: int = Field(..., ge=0, description="实际解析附图数量")
    omission_warning: str = Field(default="合规", min_length=1, description="漏看告警；无则“合规”")


class PriorArtProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prior_art_id: str = Field(
        default="D1",
        validation_alias=AliasChoices("prior_art_id", "doc_id"),
        min_length=1,
        description="现有技术编号（如 D1 或公开号）",
    )
    core_technical_problem_solved: str = Field(
        ...,
        validation_alias=AliasChoices("core_technical_problem_solved", "core_technical_summary"),
        min_length=1,
        description="该对比文件解决的技术问题及核心运作机制",
    )
    component_index: list[PriorArtComponent] = Field(default_factory=list, description="核心部件索引")
    figure_library: list[FigureLibrary] = Field(default_factory=list, description="逐图视觉库")
    reading_audit: TargetedReadingAudit = Field(..., description="定向阅读审计")

    @field_validator("prior_art_id", mode="before")
    @classmethod
    def _fill_blank_prior_art_id(cls, value: object) -> str:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        return "D1"


class PriorArtProfileSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_goal: Literal["patentability"] = Field(..., description="对比目标")
    prior_art_profiles: list[PriorArtProfile] = Field(default_factory=list, description="现有技术数字孪生档案列表")
    overall_summary: str = Field(default="未提供整体解剖总结。", min_length=1, description="整体解剖总结")


class PriorArtTargetedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_feature_id: str = Field(default="UNKNOWN_FEATURE", min_length=1, description="本案特征编号")
    target_feature_text: str = Field(default="未标注目标特征", min_length=1, description="本案特征")
    textual_verification: str = Field(default="无", min_length=1, description="文字维度核验结论")
    visual_verification: str = Field(default="无", min_length=1, description="图像维度核验结论")
    joint_conclusion: str = Field(default="未提供综合结论", min_length=1, description="图文综合结论")


class PriorArtTargetedReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_by_prior_art: bool = Field(..., description="综合判断是否被对比文件支持")
    confidence: Literal["High", "Medium", "Low"] = Field(..., description="置信度")
    items: list[PriorArtTargetedItem] = Field(default_factory=list, description="特征级图文核验项")
    overall_conclusion: str = Field(default="未提供图文核验总结。", min_length=1, description="图文核验总结")


class FeatureCollision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(..., min_length=1, description="申请人特征编号（如 F1.1）")
    prior_art_id: str = Field(..., min_length=1, description="对比文件编号（如 D1）")
    text_evidence: str = Field(..., min_length=1, description="文本证据；无则填“未在文字中发现”")
    visual_evidence: str = Field(..., min_length=1, description="视觉证据；无则填“未在附图中发现”")
    component_match_status: str = Field(..., min_length=1, description="实体部件命中状态")
    relationship_match_status: str = Field(..., min_length=1, description="连接关系/协同机理命中状态")
    disclosure_status: Literal["EXPLICIT", "IMPLICIT_VISUAL", "NOT_DISCLOSED"] = Field(..., description="公开状态")
    collision_reasoning: str = Field(..., min_length=1, description="碰撞判定理由")


class ClaimCollisionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="权利要求编号")
    feature_collisions: list[FeatureCollision] = Field(default_factory=list, description="该权利要求的特征碰撞明细")
    claim_safety_status: Literal["DESTROYED", "AT_RISK", "SAFE"] = Field(..., description="权利要求安全评估")


class FeatureCollisionMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_conclusion: str = Field(..., min_length=1, description="全局查新结论摘要")
    prior_art_targeted_report: list[ClaimCollisionReport] = Field(default_factory=list, description="逐权利要求碰撞报告")


class ClaimRiskProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_number: int = Field(..., ge=1, description="权利要求编号")
    novelty_risk: str = Field(..., min_length=1, description="新颖性风险（FATAL/SAFE）")
    inventiveness_risk: str = Field(..., min_length=1, description="创造性风险（HIGH/MEDIUM/LOW）")
    topology_difference_analysis: str = Field(
        default="未提供拓扑差异论理。",
        validation_alias=AliasChoices("topology_difference_analysis", "legal_reasoning", "reasoning"),
        min_length=1,
        description="拓扑差异论理",
    )
    breakthrough_point: str = Field(default="未明确突破口，建议人工复核。", min_length=1, description="答辩/修改突破口")
    robust_distinguishing_features: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("robust_distinguishing_features", "key_distinguishing_features"),
        description="坚挺区别技术特征",
    )

    @field_validator("topology_difference_analysis", "breakthrough_point", mode="before")
    @classmethod
    def _fill_blank_profile_text(cls, value: object, info) -> str:
        defaults = {
            "topology_difference_analysis": "未提供拓扑差异论理。",
            "breakthrough_point": "未明确突破口，建议人工复核。",
        }
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        return defaults.get(info.field_name, "未提供")


class RiskAssessmentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_risk_summary: str = Field(
        ...,
        validation_alias=AliasChoices("global_risk_summary", "overall_reasoning"),
        min_length=1,
        description="全局风险摘要",
    )
    claim_assessments: list[ClaimRiskProfile] = Field(
        default_factory=list,
        validation_alias=AliasChoices("claim_assessments", "claim_risks"),
        description="逐条权利要求风险评估",
    )
    strategic_amendment_direction: str = Field(
        default="建议优先围绕未公开拓扑关系进行权利要求限定与协同机理论证。",
        min_length=1,
        description="宏观修改战略",
    )


class AmendmentSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_claim_number: int = Field(..., ge=1, description="目标权项")
    amendment_type: str = Field(
        default="INTRODUCE_SPEC_FEATURE",
        min_length=1,
        description="修改类型：MERGE_DEPENDENT_CLAIM / INTRODUCE_SPEC_FEATURE",
    )
    source_feature_name: str = Field(default="未标注特征", min_length=1, description="引入特征名称")
    source_location: str = Field(..., min_length=1, description="原文件定位")
    verbatim_addition: str = Field(
        default="未提供可直接插入的原话片段，建议人工复核。",
        validation_alias=AliasChoices("verbatim_addition", "suggested_change"),
        min_length=1,
        description="拟加入主权的原话片段",
    )
    synergy_and_mechanism_focus: str = Field(
        default="建议围绕连接关系与协同动作构建区别机理。",
        min_length=1,
        description="机理破局说明",
    )
    draft_amended_claim_text: str = Field(
        default="未生成完整修改草案，请结合原权利要求补全。",
        min_length=1,
        description="修改后完整权利要求草案",
    )
    expected_overcoming_effect: str = Field(
        default="通过限定特定连接关系与协同机理，降低与对比文件重合风险。",
        validation_alias=AliasChoices("expected_overcoming_effect", "expected_effect"),
        min_length=1,
        description="预期规避效果",
    )


class AmendmentSuggestionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_rescue_strategy: str = Field(
        ...,
        validation_alias=AliasChoices("overall_rescue_strategy", "final_recommendation"),
        min_length=1,
        description="全案抢救战略总述",
    )
    concrete_amendments: list[AmendmentSuggestion] = Field(
        default_factory=list,
        validation_alias=AliasChoices("concrete_amendments", "suggestions"),
        description="具体修改施工单",
    )
    article_33_compliance_statement: str = Field(
        default="上述修改均来源于原申请文件记载，未引入新事项。",
        min_length=1,
        description="第33条合规声明",
    )
