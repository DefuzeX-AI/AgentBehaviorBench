from __future__ import annotations

from agents.base_agent import BaseStructuredAgent, RetryPolicy
from tools.rag_search import RAGSearchService
from workflows.oa_workflow import OAAgentBundle, build_oa_workflow


def _agent(name: str, payload: dict[str, object]):
    return BaseStructuredAgent(
        name=name,
        llm_callable=lambda _prompt, _ctx: payload,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )


def test_oa_workflow_with_new_nodes_completes() -> None:
    bundle = OAAgentBundle(
        oa_parser_agent=_agent(
            "oa-parser",
            {
                "defects": [
                    {
                        "defect_type": "缺乏创造性",
                        "rejected_claims": [1],
                        "main_cited_docs": ["D1", "D2"],
                        "feature_mappings": [
                            {
                                "target_feature": "权利要求1中的关键结构特征A",
                                "prior_art_doc": "D1",
                                "cited_paragraphs": "[0032]",
                                "cited_figures": "图2部件10",
                                "examiner_logic": "审查员认为D1图2部件10可对应本案特征A。",
                            }
                        ],
                        "combination_motivation": "D2提供改进连接结构的技术启示。",
                    }
                ],
                "overall_summary": "审查员认为权利要求1相对于D1和D2组合不具备创造性。",
            },
        ),
        multimodal_prior_art_agent=_agent(
            "multimodal-prior-art",
            {
                "examiner_conclusion_supported": True,
                "confidence": "High",
                "supporting_items": [
                    {
                        "target_feature": "权利要求1中的关键结构特征A",
                        "prior_art_text_disclosure": "D1 段落[0032]描述了对应连接结构。",
                        "prior_art_visual_disclosure": "D1 图2显示部件10为刚性圆柱件，套设于主体外周并与端面贴合连接。",
                        "amendment_avoidance_warning": "后续修改不得再使用宽泛连接件描述，应引入更具体几何限定。",
                    }
                ],
                "disputable_items": [],
                "overall_conclusion": "定点核验显示审查员主张整体成立，可进入后备特征挖掘路径。",
            },
        ),
        application_baseline_agent=_agent(
            "application-baseline",
            {
                "claims_tree": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": [],
                        "features": [{"feature_id": "1A", "feature_text": "特征A"}],
                    }
                ],
                "spec_feature_index": [
                    {
                        "component_or_step_name": "执行单元",
                        "reference_numeral": "10",
                        "detailed_description": "执行单元用于接收控制信号并输出执行动作。",
                        "alternative_embodiments": "无",
                        "source_paragraph": "说明书段落[0041]",
                    }
                ],
                "claim_tree_overview": "权利要求1为独立权利要求，权利要求2至3为从属限定，用于细化关键技术特征。",
                "normalized_claim_features": ["特征A"],
                "fallback_features": ["后备特征X"],
                "specification_feature_index": ["说明书段落[0041]"],
            },
        ),
        concession_gap_agent=_agent(
            "concession-gap",
            {
                "overall_strategy_summary": "优先合并从属权利要求，必要时再挖说明书后备特征。",
                "claim_assessments": [
                    {"claim_number": 1, "status": "DEFEATED", "reasoning": "权利要求1被D1+D2覆盖。"},
                    {"claim_number": 3, "status": "MERGE_CANDIDATE", "reasoning": "权利要求3包含未公开的锁止细节。"},
                ],
                "recommended_merges": [3],
                "mining_directives": [
                    {
                        "target_component_or_step": "锁止结构",
                        "technical_gap_to_fill": "补足对比文件中缺失的几何约束细节。",
                        "avoidance_warning": "避免宽泛弹性连接术语。",
                    }
                ],
                "failed_claims": [1],
                "confirmed_points": ["D1+D2 对当前权利要求1覆盖较强。"],
                "gap_targets": ["连接结构细化", "内部构造细化"],
                "rationale": "需要通过后备特征收窄保护范围并建立新的区别点。",
            },
        ),
        fallback_feature_miner_agent=_agent(
            "fallback-miner",
            {
                "mining_status": "SUCCESS",
                "candidates": [
                    {
                        "candidate_id": "C3",
                        "addressed_directive": "锁止结构",
                        "feature_name": "杯盖与杯体采用带弹簧的卡扣配合",
                        "reference_numeral": "20",
                        "verbatim_quote": "卡扣部设置弹性件，在闭合时提供回弹锁止力。",
                        "source_location": "说明书段落[0058]；图3",
                        "gap_filling_rationale": "该特征可补足锁止技术缺口，并与现有公开结构形成区分。",
                    }
                ],
                "mining_summary": "候选C3具备较强区分潜力，可作为后续修改权利要求的优先选择。",
            },
        ),
        prior_art_stress_tester_agent=_agent(
            "stress-tester",
            {
                "overall_survival_rate": "压测了1个特征，最终1个存活。",
                "tested_features": [
                    {
                        "candidate_id": "C3",
                        "feature_name": "杯盖与杯体采用带弹簧的卡扣配合",
                        "test_verdict": "SURVIVED",
                        "prior_art_hit_location": "无",
                        "red_team_reasoning": "D1/D2 文本与附图均未显示该卡扣结构。",
                        "rebuttal_foundation": "D1/D2未公开该结构，且该结构可提升锁止稳定性，具备答辩价值。",
                    }
                ],
                "survived_candidate_ids": ["C3"],
                "summary": "候选C3通过文本与附图双重压力测试，可作为优先修改引入特征。",
            },
        ),
        strategy_decision_agent=_agent(
            "strategy-decision",
            {
                "global_decision": "AMEND_AND_ARGUE",
                "strategy_rationale": "权利要求1被击穿，需引入压测存活特征并同步答辩。",
                "amendment_plan": {
                    "target_independent_claim": 1,
                    "amendment_tactic": "INTRODUCE_SPEC_FEATURE",
                    "source_dependent_claims": [],
                    "survived_candidate_ids": ["C3"],
                    "amendment_guidance": "将Candidate_C的原话特征插入权利要求1中。",
                },
                "rebuttal_plan": [
                    {
                        "target_claim": 1,
                        "core_argument_logic": "D1/D2未公开新增的弹簧卡扣结构，因此修改后权利要求具备创造性。",
                        "evidence_support": "节点3核验与节点6压测均支持。",
                    }
                ],
                "action": "AMEND_AND_ARGUE",
                "amendment_instruction": "将Candidate_C的原话特征插入权利要求1中。",
                "argument_logic": "D1/D2未公开新增的弹簧卡扣结构，因此修改后权利要求具备创造性。",
                "selected_candidate_ids": ["C3"],
            },
        ),
        claim_amendment_agent=_agent(
            "claim-amendment",
            {
                "is_amended": True,
                "amendment_basis_statement": "新增特征来源于说明书段落[0058]与图3，未超范围。",
                "claim_mappings": [
                    {
                        "original_claim_number": "原权利要求1",
                        "new_claim_number": "新权利要求1",
                        "amendment_type": "MODIFIED_WITH_NEW_FEATURE",
                        "amended_text": "一种系统，包含带弹簧卡扣配合结构...",
                    }
                ],
                "final_claims_text": "1. 一种系统，包含带弹簧卡扣配合结构...",
                "amended_claims": {"claims": [{"id": 1, "text": "一种系统，包含带弹簧卡扣配合结构..."}]},
                "amendment_log": ["在权利要求1加入带弹簧卡扣配合特征。"],
            },
        ),
        argument_writer_agent=_agent(
            "argument-writer",
            {
                "amendment_statement": "本案权利要求已按说明书原始记载进行修改，未超出原始公开范围，符合专利法第33条规定。",
                "arguments_by_claim": [
                    {
                        "target_claim": 1,
                        "closest_prior_art": "对比文件1（D1）",
                        "distinguishing_features": "修改后的权利要求1引入带弹簧卡扣配合结构，与D1现有结构不同。",
                        "technical_problem_solved": "该区别特征用于提升锁止稳定性并改善密封可靠性。",
                        "non_obviousness_logic": "D1/D2均未给出将该结构引入当前方案的技术启示，本领域技术人员无动机进行该改进。",
                        "legal_conclusion": "因此权利要求1具备创造性，符合专利法第22条第3款规定。",
                    }
                ],
                "final_reply_text": "本案权利要求已按说明书原始记载进行修改，未超出原始公开范围，符合专利法第33条规定。关于权利要求1，最接近现有技术为D1，修改后引入带弹簧卡扣配合结构并解决锁止稳定性问题，D1/D2无结合启示，故具备创造性。",
                "argument_text": "本案权利要求已按说明书原始记载进行修改，未超出原始公开范围，符合专利法第33条规定。关于权利要求1，最接近现有技术为D1，修改后引入带弹簧卡扣配合结构并解决锁止稳定性问题，D1/D2无结合启示，故具备创造性。",
                "key_points": ["区别特征明确", "技术问题清晰", "无结合启示"],
            },
        ),
        spec_update_agent=_agent(
            "spec-update",
            {
                "requires_spec_update": False,
                "amendment_items": [],
                "article_33_declaration": "本轮无需进行说明书适应性修改，未引入新的技术内容，符合《专利法》第33条规定。",
                "applied": False,
                "changes": [],
                "updated_excerpt": "",
            },
        ),
        response_traceability_agent=_agent(
            "response-traceability",
            {
                "global_go_no_go": "GO",
                "support_basis_audit": [
                    {
                        "severity": "PASS",
                        "risk_category": "A26.4_UNSUPPORTED",
                        "problematic_text": "无",
                        "audit_reasoning": "新增特征具备说明书原始支持。",
                        "suggested_remedy": "无",
                    }
                ],
                "logic_consistency_audit": [],
                "harmful_admission_audit": [],
                "final_strategy_summary": "经终审风控核验，当前答复方案整体可提交。",
                "claim_support_ok": True,
                "logic_consistency_ok": True,
                "findings": [],
                "final_risk_summary": "风险可控，建议人工复核。",
            },
        ),
        rag_service=RAGSearchService(),
    )

    graph = build_oa_workflow(bundle)
    output = graph.invoke(
        {
            "session_id": "s-oa-mm",
            "trace_id": "t-oa-mm",
            "status": "running",
            "current_step": "application_baseline_node",
            "oa_text": "审查员引用 D1 图2 进行创造性评价。",
            "original_claims": {"claims": [{"id": 1, "text": "一种系统..."}]},
            "application_specification": {"text": "说明书内容"},
            "prior_arts_paths": [],
            "parsed_defects": None,
            "retrieved_contexts": [],
            "prior_art_targeted_report": None,
            "application_baseline": None,
            "concession_gap_report": None,
            "mined_fallback_features": None,
            "stress_test_report": None,
            "strategy_decision": None,
            "rebuttal_plan": None,
            "amended_claims": None,
            "argument_draft": None,
            "spec_update_note": None,
            "response_traceability": None,
            "comparison_result": None,
            "visual_report": None,
            "application_images": [],
            "prior_art_images": [],
            "vision_warnings": [],
            "final_strategy": None,
            "final_reply_text": None,
            "error_count": 0,
            "tool_error_count": 0,
            "last_error": None,
            "node_latency_ms": 0,
        }
    )

    assert output.get("status") == "completed"
    assert isinstance(output.get("prior_art_targeted_report"), dict)
    assert isinstance(output.get("strategy_decision"), dict)
    assert isinstance(output.get("response_traceability"), dict)
