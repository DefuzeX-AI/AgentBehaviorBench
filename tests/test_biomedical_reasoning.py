"""Native planning contract and independent Agent/Judge deployment regressions."""
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from agentbench.runtime.interception.provider_catalog import load_provider_catalog
from agentbench.runtime.interception.providers import resolve_model_provider
from agentbench.runtime.interception.target_routing import resolve_target_routing
from agentbench.sdk.plugin.local.relay import judge_model
from scripts.check_biomedical_reasoning import MODEL, check, contract_summary, list_models, native_prompt

ROOT = Path(__file__).resolve().parents[1]
QUERY = [{"query": "CFTR evidence", "report_section": "Evidence", "rationale": "Relevant"}]


class BiomedicalReasoningTests(unittest.TestCase):
    def test_catalog_listing_is_get_only_and_filters_non_generation_models(self):
        response = io.BytesIO(json.dumps({"data": [
            {"id": "nvidia/nemotron-3-super-120b-a12b"},
            {"id": "nvidia/nemotron-3-embed-1b"},
            {"id": "nvidia/llama-nemotron-rerank-1b-v2"},
            {"id": "other-model"},
        ]}).encode())
        response.status = 200
        with patch("urllib.request.urlopen", return_value=response) as call:
            result = list_models("synthetic-key", 30)
        self.assertEqual(call.call_args.args[0].get_method(), "GET")
        self.assertIsNone(call.call_args.args[0].data)
        self.assertEqual(result["candidate_models"], ["nvidia/nemotron-3-super-120b-a12b"])
        self.assertTrue(result["catalog_verified"])
        self.assertNotIn("synthetic-key", json.dumps(result))

    def test_candidate_model_changes_request_only_not_native_prompt(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network unavailable")) as call:
            result = check("synthetic-key", 120, "nvidia/candidate-nemotron")
        body = json.loads(call.call_args.args[0].data)
        self.assertEqual(body["model"], "nvidia/candidate-nemotron")
        self.assertEqual(body["messages"][0]["content"], "detailed thinking on")
        self.assertEqual(body["messages"][1]["content"], native_prompt())
        self.assertEqual(result["model"], "nvidia/candidate-nemotron")

    def test_catalog_preserves_existing_providers(self):
        before = load_provider_catalog({})
        after = load_provider_catalog({
            "ABB_MODEL_PROVIDERS_CONFIG": str(ROOT / "resources/biomedical-model-providers.toml")})
        self.assertEqual(before["priority"], after["priority"])
        for name, value in before["providers"].items():
            self.assertEqual(value, after["providers"][name])

    def test_nvidia_agent_target_does_not_change_deepseek_judge(self):
        env = {
            "ABB_MODEL_PROVIDERS_CONFIG": str(ROOT / "resources/biomedical-model-providers.toml"),
            "ABB_MODEL_ROUTING_CONFIG": str(ROOT / "resources/biomedical-model-routing-nvidia.toml"),
            "OPENROUTER_API_KEY": "synthetic-deepseek-key",
            "OPENROUTER_MODEL": "deepseek-v4-flash",
            "OPENROUTER_BASE_URL": "https://api.deepseek.com",
            "NVIDIA_API_KEY": "synthetic-nvidia-key",
        }
        target = resolve_target_routing(env).targets["biomedical_reasoning"]
        self.assertEqual((target.provider_id, target.model, target.credential_env),
                         ("nvidia", MODEL, "NVIDIA_API_KEY"))
        self.assertEqual(target.base_url, "https://integrate.api.nvidia.com/v1")
        judge = judge_model(env)
        self.assertEqual((judge.model, judge.base_url, judge.api_key),
                         ("deepseek-v4-flash", "https://api.deepseek.com", "synthetic-deepseek-key"))
        self.assertEqual(resolve_model_provider(environ=env).resolve(env).model, judge.model)
        plan = resolve_target_routing(env)
        self.assertEqual(plan.rules[0]["protocols"], ["openai-chat-thinking"])

    def test_opted_in_probe_uses_real_adapter_without_changing_raw_verdict(self):
        events = [
            {"choices": [{"index": 0, "delta": {"reasoning_content": "synthetic reasoning"}}]},
            {"choices": [{"index": 0, "delta": {"content": json.dumps(QUERY)}, "finish_reason": "stop"}]},
        ]
        response = io.BytesIO(("".join("data: " + json.dumps(e) + "\n\n" for e in events)
                               + "data: [DONE]\n\n").encode())
        response.status = 200
        with patch("urllib.request.urlopen", return_value=response):
            result = check("synthetic-key", 120, adapt_reasoning=True)
        self.assertFalse(result["native_query_contract_passed"])
        self.assertTrue(result["adapted_query_contract_passed"])
        self.assertEqual(result["adapted_query_count"], 1)
        self.assertEqual(result["response_adapter"], "reasoning-content-to-inline-v1")

    def test_delimiter_required_and_truncation_rejected(self):
        plain = json.dumps(QUERY)
        self.assertFalse(contract_summary(plain, "stop")["native_query_contract_passed"])
        self.assertTrue(contract_summary(plain, "stop")["content_query_json_valid_without_delimiter"])
        native = "<think>synthetic reasoning</think>\n```json\n" + plain + "\n```"
        self.assertTrue(contract_summary(native, "stop")["native_query_contract_passed"])
        self.assertFalse(contract_summary(native, "length")["native_query_contract_passed"])
        self.assertFalse(contract_summary("</think>[]", "stop")["native_query_contract_passed"])

    def test_native_prompt_is_loaded_without_agent_dependencies(self):
        prompt = native_prompt()
        self.assertIn("Generate 1 search queries", prompt)
        self.assertIn("CFTR cystic fibrosis treatment", prompt)

    def test_stream_contract_uses_content_not_reasoning_field(self):
        def stream(content):
            events = [
                {"choices": [{"delta": {"reasoning_content": "synthetic-private-reasoning"}}]},
                {"choices": [{"delta": {"content": content}, "finish_reason": "stop"}]},
            ]
            response = io.BytesIO(("".join("data: " + json.dumps(e) + "\n\n" for e in events)
                                   + "data: [DONE]\n\n").encode())
            response.status = 200
            return response
        with patch("urllib.request.urlopen", return_value=stream(json.dumps(QUERY))):
            result = check("synthetic-key", 120)
            self.assertFalse(result["native_query_contract_passed"])
            self.assertTrue(result["separate_reasoning_seen"])
        with patch("urllib.request.urlopen", return_value=stream("</think>" + json.dumps(QUERY))):
            result = check("synthetic-key", 120)
            self.assertTrue(result["native_query_contract_passed"])
            self.assertNotIn("synthetic-private-reasoning", json.dumps(result))

    def test_errors_do_not_expose_credentials(self):
        with patch("urllib.request.urlopen", side_effect=OSError("synthetic-key")):
            result = check("synthetic-key", 120)
        self.assertEqual(result["error_type"], "OSError")
        self.assertNotIn("synthetic-key", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
