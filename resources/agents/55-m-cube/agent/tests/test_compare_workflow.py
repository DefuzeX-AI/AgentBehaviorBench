from __future__ import annotations

from agents.base_agent import BaseStructuredAgent, RetryPolicy
from tools.rag_search import RAGSearchService
from workflows.compare_workflow import CompareAgentBundle, build_compare_workflow


def _agent(name: str, payload: dict[str, object]):
    return BaseStructuredAgent(
        name=name,
        llm_callable=lambda _prompt, _ctx: payload,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )


def test_compare_workflow_completes() -> None:
    bundle = CompareAgentBundle(
        draft_parser_agent=_agent(
            "compare-draft-parser",
            {
                "claims_tree": [
                    {
                        "claim_number": 1,
                        "is_independent": True,
                        "dependency": [],
                        "atomic_features": [
                            {
                                "feature_id": "F1.1",
                                "verbatim_text": "特征A",
                                "entity_components": ["部件A"],
                                "connection_and_synergy": "部件A与连接杆固定配合形成限位关系。",
                                "visual_anchor": {
                                    "reference_numeral": "10",
                                    "figure_labels": ["图1"],
                                    "visual_morphology": "部件A位于主体左侧并与连接杆固定。",
                                },
                            }
                        ],
                    }
                ],
                "fallback_feature_index": [
                    {
                        "feature_name": "后备部件X",
                        "verbatim_quote": "后备部件X设置于主体底部，用于提高稳定性。",
                        "connection_and_synergy": "后备部件X贴合底部壳体并与支撑面协同抑制晃动。",
                        "source_location": "说明书[0035]",
                        "visual_anchor": {
                            "reference_numeral": "10",
                            "figure_labels": ["图2"],
                            "visual_morphology": "部件X位于底部中心位置，外周与壳体贴合。",
                        },
                    }
                ],
            },
        ),
        prior_art_parser_agent=_agent(
            "compare-prior-art-parser",
            {
                "comparison_goal": "patentability",
                "prior_art_profiles": [
                    {
                        "prior_art_id": "D2",
                        "core_technical_problem_solved": "D1公开了基础结构A与配套连接方案。",
                        "component_index": [
                            {
                                "component_name": "结构A",
                                "reference_numeral": "10",
                                "structural_connections_and_mechanisms": "说明书第[0021]段记载部件10固定在壳体内用于实现结构A。",
                                "visual_appearance": "图2可见部件10呈柱状并与外壳固定。",
                            }
                        ],
                        "figure_library": [
                            {
                                "figure_label": "图2",
                                "observed_components": ["10"],
                                "visual_connections": [
                                    {
                                        "source_component": "部件10",
                                        "target_component": "壳体",
                                        "kinematic_relationship": "部件10与壳体固定连接，无相对运动。",
                                    }
                                ],
                            }
                        ],
                        "reading_audit": {
                            "input_image_count": 2,
                            "actually_used_image_count": 2,
                            "omission_warning": "合规",
                        },
                    }
                ],
                "overall_summary": "对比文件对核心结构覆盖较强，需要进一步限定。",
            },
        ),
        matrix_comparison_agent=_agent(
            "compare-matrix",
            {
                "global_conclusion": "独立权利要求关键特征被D1命中。",
                "prior_art_targeted_report": [
                    {
                        "claim_number": 1,
                        "feature_collisions": [
                            {
                                "feature_id": "F1.1",
                                "prior_art_id": "D2",
                                "text_evidence": "D1[0021]",
                                "visual_evidence": "D1图2",
                                "component_match_status": "命中，D1公开部件A及关联结构。",
                                "relationship_match_status": "命中，D1中部件A与壳体连接关系与本案一致。",
                                "disclosure_status": "EXPLICIT",
                                "collision_reasoning": "图文均有对应公开。",
                            }
                        ],
                        "claim_safety_status": "DESTROYED",
                    }
                ],
            },
        ),
        risk_assessment_agent=_agent(
            "compare-risk",
            {
                "global_risk_summary": "当前整体风险较高，建议修改独立权利要求。",
                "claim_assessments": [
                    {
                        "claim_number": 1,
                        "novelty_risk": "FATAL",
                        "inventiveness_risk": "HIGH",
                        "topology_difference_analysis": "D1对现有连接拓扑公开充分，本案差异集中在次级连接细节。",
                        "breakthrough_point": "将后备部件X的协同限位机理并入主权项形成新拓扑关系。",
                        "robust_distinguishing_features": ["后备部件X与壳体之间的协同限位连接机理"],
                    }
                ],
                "strategic_amendment_direction": "优先把后备部件X的协同限位机理加入独立权利要求。",
            },
        ),
        amendment_suggestion_agent=_agent(
            "compare-amendment",
            {
                "overall_rescue_strategy": "优先补强后备部件X的协同限位机理。",
                "concrete_amendments": [
                    {
                        "target_claim_number": 1,
                        "amendment_type": "INTRODUCE_SPEC_FEATURE",
                        "source_feature_name": "后备部件X协同限位机理",
                        "source_location": "说明书[0035]",
                        "verbatim_addition": "后备部件X贴合底部壳体并与支撑面协同抑制晃动。",
                        "synergy_and_mechanism_focus": "通过协同限位关系形成区别于D1的拓扑机理。",
                        "draft_amended_claim_text": "根据权利要求1所述装置，其特征在于，后备部件X贴合底部壳体并与支撑面协同抑制晃动。",
                        "expected_overcoming_effect": "通过引入协同限位关系降低重合风险。",
                    }
                ],
                "article_33_compliance_statement": "上述修改均有原申请文件依据，未引入新事项。",
            },
        ),
        rag_service=RAGSearchService(),
    )
    graph = build_compare_workflow(bundle)
    output = graph.invoke(
        {
            "session_id": "s-compare-1",
            "trace_id": "t-compare-1",
            "status": "running",
            "current_step": "multimodal_draft_parser_node",
            "comparison_goal": "patentability",
            "original_claims": {"text": "权利要求书..."},
            "application_specification": {"text": "说明书..."},
            "prior_arts_paths": [],
            "application_images": [],
            "prior_art_images": [],
            "vision_warnings": [],
            "draft_baseline": None,
            "prior_art_profiles": None,
            "feature_collision_matrix": None,
            "risk_report": None,
            "amendment_suggestions": None,
            "final_compare_report": None,
            "prior_art_targeted_report": None,
            "targeted_reading_audit": None,
            "retrieved_contexts": [],
            "error_count": 0,
            "tool_error_count": 0,
            "last_error": None,
            "node_latency_ms": 0,
        }
    )

    assert output.get("status") == "completed"
    assert isinstance(output.get("draft_baseline"), dict)
    assert isinstance(output.get("prior_art_profiles"), dict)
    assert isinstance(output.get("feature_collision_matrix"), dict)
    assert isinstance(output.get("prior_art_targeted_report"), list)
    assert isinstance(output.get("risk_report"), dict)
    assert isinstance(output.get("amendment_suggestions"), dict)
    profiles = (output.get("prior_art_profiles") or {}).get("prior_art_profiles", [])
    assert profiles and profiles[0].get("prior_art_id") == "D1"
    reports = (output.get("feature_collision_matrix") or {}).get("prior_art_targeted_report", [])
    collisions = reports[0].get("feature_collisions", []) if reports else []
    assert collisions and collisions[0].get("prior_art_id") == "D1"
