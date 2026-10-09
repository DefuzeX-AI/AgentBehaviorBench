from __future__ import annotations

from agents.base_agent import BaseStructuredAgent, RetryPolicy
from workflows.polish_workflow import PolishAgentBundle, build_polish_workflow


def _agent(name: str, payload: dict[str, object]):
    return BaseStructuredAgent(
        name=name,
        llm_callable=lambda _prompt, _ctx: payload,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )


def test_polish_workflow_loop_then_pass() -> None:
    review_calls = {"n": 0}

    def _review_callable(_prompt: str, _ctx: dict[str, object]) -> dict[str, object]:
        review_calls["n"] += 1
        if review_calls["n"] == 1:
            return {
                "pass_gate": False,
                "issues": [
                    {
                        "severity": "high",
                        "weakness_type": "创造性不足",
                        "description": "主权机理限定仍偏弱。",
                        "counter_strategy": "补强径向错位锁定协同动作。",
                    }
                ],
                "return_instruction": "请在主权增加径向错位锁定机理。",
                "final_judgement": "未通过，建议回退至权利要求重构节点补强。",
            }
        return {
            "pass_gate": True,
            "issues": [],
            "return_instruction": "通过，无需回退。",
            "final_judgement": "通过终审。",
        }

    bundle = PolishAgentBundle(
        diagnostic_agent=_agent(
            "polish-diagnostic",
            {
                "overview": "存在主权机理表达不足。",
                "wide_scope_issues": [],
                "dependent_gap_issues": [],
                "effect_gap_issues": [],
                "key_repair_targets": ["主权补强"],
            },
        ),
        synergy_miner_agent=_agent(
            "polish-vault",
            {
                "vault_summary": "已提取高价值机理。",
                "high_value_features": [
                    {
                        "feature_name": "径向错位锁定",
                        "source_location": "说明书[0035]",
                        "verbatim_quote": "限位件沿径向穿设于导向槽并在相对转动时形成错位自锁。",
                        "connection_and_synergy": "径向穿设与相对转动配合形成动态锁定。",
                        "value_score": "high",
                        "recommended_usage": "主权",
                    }
                ],
            },
        ),
        claim_architect_agent=_agent(
            "polish-claims",
            {
                "architecture_summary": "已重构权利要求。",
                "rebuilt_claims": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": [],
                        "draft_text": "一种装置，其特征在于限位件径向穿设并形成错位自锁。",
                        "added_mechanisms": ["错位自锁"],
                        "source_basis": ["说明书[0035]"],
                    }
                ],
                "optimized_claims_text": "1. 一种装置，其特征在于限位件径向穿设并形成错位自锁。",
                "article_33_basis": "来源于说明书[0035]。",
            },
        ),
        specification_amplifier_agent=_agent(
            "polish-spec",
            {
                "amplification_summary": "已补强机理与效果。",
                "mechanism_effect_map": [
                    {
                        "feature_name": "错位自锁",
                        "mechanism_explanation": "限位件与导向槽通过径向错位形成锁定。",
                        "technical_effect": "降低松脱风险。",
                    }
                ],
                "optimized_specification_text": "通过径向错位自锁降低松脱风险。",
            },
        ),
        adversarial_reviewer_agent=BaseStructuredAgent(
            name="polish-review",
            llm_callable=_review_callable,
            retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
        ),
    )
    graph = build_polish_workflow(bundle)
    output = graph.invoke(
        {
            "session_id": "s-polish-1",
            "trace_id": "t-polish-1",
            "status": "running",
            "current_step": "diagnostic_analyzer_node",
            "original_claims": {"text": "权利要求书"},
            "application_specification": {"text": "说明书"},
        }
    )

    assert output.get("status") == "completed"
    assert review_calls["n"] == 2
    assert isinstance(output.get("polish_final_package"), dict)
    assert int(output.get("polish_revision_count", 0)) >= 1


def test_polish_workflow_circuit_breaker() -> None:
    bundle = PolishAgentBundle(
        diagnostic_agent=_agent(
            "polish-diagnostic",
            {
                "overview": "存在问题。",
                "wide_scope_issues": [],
                "dependent_gap_issues": [],
                "effect_gap_issues": [],
                "key_repair_targets": [],
            },
        ),
        synergy_miner_agent=_agent(
            "polish-vault",
            {
                "vault_summary": "特征库。",
                "high_value_features": [],
            },
        ),
        claim_architect_agent=_agent(
            "polish-claims",
            {
                "architecture_summary": "重构完成。",
                "rebuilt_claims": [],
                "optimized_claims_text": "1. 一种装置……",
                "article_33_basis": "来源于原文。",
            },
        ),
        specification_amplifier_agent=_agent(
            "polish-spec",
            {
                "amplification_summary": "扩写完成。",
                "mechanism_effect_map": [],
                "optimized_specification_text": "说明书优化稿。",
            },
        ),
        adversarial_reviewer_agent=_agent(
            "polish-review",
            {
                "pass_gate": False,
                "issues": [
                    {
                        "severity": "high",
                        "weakness_type": "创造性不足",
                        "description": "仍可被拼凑。",
                        "counter_strategy": "继续引入更具体机理。",
                    }
                ],
                "return_instruction": "继续补强主权机理。",
                "final_judgement": "未通过。",
            },
        ),
    )
    graph = build_polish_workflow(bundle)
    output = graph.invoke(
        {
            "session_id": "s-polish-2",
            "trace_id": "t-polish-2",
            "status": "running",
            "current_step": "diagnostic_analyzer_node",
            "original_claims": {"text": "权利要求书"},
            "application_specification": {"text": "说明书"},
        }
    )

    assert output.get("status") == "completed"
    assert isinstance(output.get("polish_final_package"), dict)
    assert int(output.get("polish_revision_count", 0)) >= 3
