from __future__ import annotations

from pydantic import ValidationError

from agents.base_agent import BaseStructuredAgent, RetryPolicy
from models.draft_schemas import ClaimsSet, Specification, TechSummary
from models.image_schemas import DrawingMap, PriorArtVisualReport
from models.oa_schemas import ComparisonResult
from models.polish_schemas import ClaimArchitecturePlan


def test_tech_summary_validation_failure() -> None:
    try:
        TechSummary.model_validate(
            {
                "source_quotes": [],
                "background_and_core_problems": ["问题1", "问题2"],
                "core_solution_overview": "too short",
                "detailed_features": [],
                "overall_advantages": ["优势1"],
            }
        )
    except ValidationError as exc:
        assert "background_and_core_problems" in str(exc)
    else:
        raise AssertionError("ValidationError expected")


def test_base_agent_retry_then_success() -> None:
    calls = {"count": 0}

    def flaky_llm(_: str, __: dict[str, object]):
        calls["count"] += 1
        if calls["count"] < 3:
            return {"claims": []}
        return {
            "claims": [
                {
                    "claim_number": 1,
                    "claim_type": "independent",
                    "depends_on": [],
                    "preamble": "一种设备",
                    "transition": "其特征在于，包括：",
                    "elements": ["一个控制模块", "一个反馈模块"],
                    "full_text": "一种设备，其特征在于，包括：一个控制模块；一个反馈模块。",
                }
            ],
        }

    agent = BaseStructuredAgent[ClaimsSet](
        name="test_agent",
        llm_callable=flaky_llm,
        retry_policy=RetryPolicy(max_retries=3, initial_backoff_seconds=0, backoff_multiplier=1),
    )
    result = agent.run_structured(prompt="x", output_model=ClaimsSet)
    assert result.claims[0].claim_number == 1
    assert calls["count"] == 3


def test_drawing_map_schema_validation_success() -> None:
    drawing_map = DrawingMap.model_validate(
        {
            "figures": [
                {
                    "figure_id": "Fig.1",
                    "title": "系统结构示意图",
                    "summary": "图1展示了底座、弹簧和连接件的整体结构关系。",
                    "reference_numerals": [{"numeral": "10", "part_name": "底座", "confidence": 0.95}],
                    "relations": [
                        {
                            "subject_numeral": "20",
                            "predicate": "connected_to",
                            "object_numeral": "10",
                            "evidence": "弹簧(20)连接到底座(10)。",
                        }
                    ],
                }
            ],
            "overall_notes": "附图标记与交底文本一致。",
            "warnings": [],
        }
    )
    assert drawing_map.figures[0].reference_numerals[0].numeral == "10"


def test_specification_accepts_nested_sections() -> None:
    spec = Specification.model_validate(
        {
            "title": "一种多级控制系统",
            "technical_field": "本发明涉及工业自动控制技术领域，尤其涉及一种可闭环调节的多级控制系统。",
            "background_art": "现有技术在复杂工况下往往采用固定参数控制策略，难以根据状态变化进行动态调节，导致系统波动明显、"
            "稳定性不足且维护成本较高。与此同时，传统方案对异常状态的识别和响应存在滞后，执行单元之间协同控制能力不足，"
            "在连续运行场景中容易产生累计误差，进而影响设备可靠性并增加人工维护工作量。",
            "invention_content": {
                "technical_problem": "为了解决现有技术中稳定性不足、异常响应迟滞和维护成本偏高的技术问题，本发明提出一种多级控制系统。",
                "technical_solution": "本发明提供一种多级控制系统，包括反馈单元、执行单元和协同调节模块。反馈单元用于实时采集运行状态并识别异常，"
                "协同调节模块用于根据反馈结果动态修正控制参数，执行单元用于依据更新参数执行控制动作并回传结果，"
                "从而形成连续闭环调节机制并在多工况场景下保持系统稳定。",
                "beneficial_effects": "本发明通过闭环联动可显著提升系统稳态保持能力，通过异常触发下的参数修正可提升响应及时性，"
                "并通过多级执行协同降低长期波动与人工维护频次，从而改善整体可靠性并降低运维成本。",
            },
            "drawings_description": "图1为系统结构示意图。",
            "detailed_implementation": {
                "introductory_boilerplate": "为了使本发明的目的、技术方案及优点更加清楚明白，以下结合附图和实施例进行详细说明。",
                "overall_architecture": "系统由反馈单元10、执行单元20和协同调节模块30构成闭环架构。反馈单元10与执行单元20连接并采集状态数据，"
                "协同调节模块30接收状态数据后计算修正参数并下发至执行单元20，执行结果再回传形成完整闭环。",
                "component_details": [
                    {
                        "feature_name": "反馈单元10",
                        "structure_and_connection": "反馈单元10包括采集子模块和检测子模块，与执行单元20信号连接并与协同调节模块30数据连接。",
                        "working_principle": "反馈单元10负责状态监测和偏差识别，为参数修正提供实时依据。",
                    }
                ],
                "workflow_description": "系统启动后先采集状态并建立基线，执行单元20按初始参数运行并回传结果；当检测到偏差超限时，"
                "协同调节模块30触发修正并更新参数，执行单元20按新参数执行，反馈单元继续采集并评估收敛情况，"
                "系统按该流程循环迭代直至偏差稳定在预设范围内，从而完成连续闭环控制。",
                "alternative_embodiments": "在不脱离本发明构思前提下，检测算法与执行机构可采用本领域常规等效替换方案，"
                "例如传感器类型、驱动机构形式和参数计算方法均可进行工程化替换。",
            },
        }
    )
    assert spec.title == "一种多级控制系统"


def test_oa_comparison_result_accepts_visual_report() -> None:
    visual_report = PriorArtVisualReport.model_validate(
        {
            "cited_figure_refs": ["D1 Fig.2"],
            "diffs": [
                {
                    "feature_name": "连接结构",
                    "application_evidence": "本申请图2显示部件A与部件B为刚性连接。",
                    "prior_art_evidence": "D1图2显示部件A与部件B为可拆卸连接。",
                    "difference_assessment": "两者连接关系不同，导致结构稳定性和维护方式存在实质差异。",
                }
            ],
            "conclusion": "D1图2未公开本申请的刚性连接关系。",
        }
    )
    comparison = ComparisonResult.model_validate(
        {
            "feature_diffs": ["连接关系不同"],
            "supporting_evidence": [],
            "visual_report": visual_report.model_dump(),
        }
    )
    assert comparison.visual_report is not None
    assert comparison.visual_report.cited_figure_refs[0] == "D1 Fig.2"


def test_base_agent_repairs_missing_required_field_for_schema_drift() -> None:
    def drift_llm(_: str, __: dict[str, object]):
        return {
            "architecture_summary": "已完成重构",
            "rebuilt_claims": [],
            "optimized_claims_text": "1. 一种装置，其特征在于……",
            # article_33_basis intentionally missing
            "unexpected_extra_key": "should be dropped",
        }

    agent = BaseStructuredAgent[ClaimArchitecturePlan](
        name="test_polish_repair_agent",
        llm_callable=drift_llm,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )
    result = agent.run_structured(prompt="x", output_model=ClaimArchitecturePlan)
    assert isinstance(result.article_33_basis, str)
    assert len(result.article_33_basis) > 0


def test_base_agent_json_repair_roundtrip_on_malformed_string() -> None:
    calls = {"count": 0}

    def llm_with_bad_json_then_repair(prompt: str, _: dict[str, object]):
        calls["count"] += 1
        if "You are a JSON repair tool." in prompt:
            return {
                "claims": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": [],
                        "preamble": "一种装置",
                        "transition": "其特征在于，包括：",
                        "elements": ["一个控制模块"],
                        "full_text": "一种装置，其特征在于，包括：一个控制模块。",
                    }
                ]
            }
        # malformed JSON (missing colon) to trigger parser failure
        return '{"claims" [ {"claim_number":1} ]}'

    agent = BaseStructuredAgent[ClaimsSet](
        name="test_json_repair_agent",
        llm_callable=llm_with_bad_json_then_repair,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )
    result = agent.run_structured(prompt="x", output_model=ClaimsSet)
    assert result.claims[0].claim_number == 1
    assert calls["count"] >= 2
