"""Real OTel/KUMA and nested LangGraph boundary checks; no model/network calls.

Small real graphs validate propagation, not acceptance of the native AIRA Agent.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kuma.otel import configure_trace_evidence
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from agentbench.observe.invocation import InvocationObservation

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources/agents/41-biomedical-aiq-research-agent"


def binding():
    spec = importlib.util.spec_from_file_location("biomedical_trace_binding", UNIT / "bindings/bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TraceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.provider = TracerProvider(resource=Resource({"service.name": "abb-evaluation"}))
        self.addCleanup(self.provider.shutdown)
        self.capture = configure_trace_evidence(self.provider)
        self.capture.begin_step("run", "case", "step")
        self.observation = InvocationObservation(self.folder, "invoke", "run", "langgraph",
            context={"case_id": "case", "input_id": "step", "agent_id": "biomedical"},
            provider=self.provider)
        self.addCleanup(self.observation.close)

    def evidence(self):
        self.observation.close()
        result = self.capture.prepare_step("run", "case", "step")
        self.addCleanup(result.abort)
        return result

    def local_spans(self):
        return [json.loads(line)["data"] for line in (self.folder / "otel.jsonl").read_text().splitlines()]

    def test_sdk_safe_metadata_preserves_full_local_correlation_and_payloads(self):
        store = self.observation.store
        store.record("execution_start", input="real input")
        store.record("span_start", span_id="tool", kind="tool", name="calculate",
                     input={"a": 1}, tool_call_id="tool-id")
        store.record("span_end", span_id="tool", output={"result": 2})
        store.record("execution_end", output="real output")
        evidence = self.evidence()
        self.assertEqual(evidence.component.status, "complete")
        self.assertEqual(evidence.dropped_count, 0)
        self.assertEqual(evidence.evidence["reasons"], [])
        self.assertEqual(len(evidence.evidence["spans"]), 2)
        local = self.local_spans()
        for span in local:
            attrs = span["attributes"]
            self.assertEqual(attrs["abb.invocation_id"], "invoke")
            self.assertEqual(attrs["abb.case_id"], "case")
            for label in ("input", "output"):
                self.assertTrue((self.folder / attrs[f"abb.{label}_ref"]).is_file())
        self.assertFalse(self.observation.store.otel.exporter.local_attributes)

    def test_existing_forbidden_external_attribute_is_still_partial(self):
        self.observation.store.record("execution_start", input="input")
        span = self.provider.get_tracer("external").start_span("external")
        span.set_attribute("unknown.external.attribute", "not allowlisted")
        span.end()
        self.observation.store.record("execution_end", output="output")
        evidence = self.evidence()
        self.assertEqual(evidence.component.status, "partial")
        self.assertIn("trace_attribute_not_allowlisted", evidence.evidence["reasons"])

    def test_actual_model_callback_bodies_are_present_not_fabricated(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.outputs import LLMResult, ChatGeneration
        store = self.observation.store
        store.record("execution_start", input="input")
        callback = self.observation.callbacks[0]
        callback.on_chat_model_start({}, [[HumanMessage(content="actual question")]],
                                     run_id="model", name="native_model")
        callback.on_llm_end(LLMResult(generations=[[
            ChatGeneration(message=AIMessage(content="actual answer"))]]), run_id="model")
        store.record("execution_end", output="actual answer")
        evidence = self.evidence()
        model = next(s for s in evidence.evidence["spans"] if s["name"] == "native_model")
        self.assertEqual(evidence.component.status, "complete")
        self.assertEqual(model["model_content"]["input"]["status"], "present")
        self.assertEqual(model["model_content"]["output"]["status"], "present")
        self.assertIn("actual question", json.dumps(model["model_content"]["input"]))
        self.assertIn("actual answer", json.dumps(model["model_content"]["output"]))

    def test_unfinished_span_remains_incomplete_not_relabelled(self):
        self.observation.store.record("execution_start", input="input")
        self.observation.store.record("span_start", span_id="unfinished", name="pending")
        self.observation.close()
        status = json.loads((self.folder / "otel-status.json").read_text())
        self.assertEqual(status["status"], "incomplete")
        self.assertEqual(status["unfinished_spans"], 1)
        unfinished = next(s for s in self.local_spans() if s["name"] == "pending")
        self.assertTrue(unfinished["attributes"]["abb.incomplete"])
        self.assertEqual(unfinished["status"]["status_code"], "ERROR")

    def test_binding_propagates_real_nested_graph_callbacks_and_keeps_native_config(self):
        module = binding()
        captured = []
        async def node(state, config):
            captured.append((state, config["configurable"]["native_value"]))
            return {"result": "Native report"}
        graph = StateGraph(dict)
        graph.add_node("native_node", node)
        graph.add_edge(START, "native_node")
        graph.add_edge("native_node", END)
        compiled = graph.compile()
        async def run_native(message):
            # Mirror the native functions' explicit graph config; the public
            # inherited callback context must survive this inner argument.
            result = await compiled.ainvoke({"message": message},
                config={"configurable": {"native_value": "native"}})
            return result["result"]
        with patch.object(module, "_install_secret_filter"):
            agent = module.create_graph()
        agent._run_native = run_native
        value = json.dumps({"topic": "CFTR", "report_organization": "Evidence",
            "search_web": False, "rag_collection": "Biomedical_Dataset",
            "num_queries": 1, "llm_name": "nemotron"})
        self.observation.store.record("execution_start", input=value)
        config = self.observation.config({"configurable": {"native_value": "must-not-override"}})
        output = asyncio.run(agent.ainvoke(value, config=config))
        self.observation.store.record("execution_end", output=output)
        evidence = self.evidence()
        self.assertEqual(output, {"report": "Native report"})
        self.assertEqual(captured[0][1], "native")
        self.assertEqual(json.loads(captured[0][0]["message"]), json.loads(value))
        names = [s["name"] for s in evidence.evidence["spans"]]
        self.assertIn("biomedical.native_workflow", names)
        self.assertIn("native_node", names)
        self.assertGreater(len(names), 2)
        self.assertEqual(evidence.component.status, "complete")
        root = next(s for s in evidence.evidence["spans"] if s["name"] == "abb.execute")
        wrapper = next(s for s in evidence.evidence["spans"] if s["name"] == "biomedical.native_workflow")
        self.assertEqual(wrapper["parent_span_id"], root["span_id"])

    def test_binding_preserves_native_exception_and_closes_callback_span(self):
        module = binding()
        async def run_native(message):
            raise ValueError("native failure")
        with patch.object(module, "_install_secret_filter"):
            agent = module.create_graph()
        agent._run_native = run_native
        context = {"report_organization": "Evidence", "search_web": False,
            "rag_collection": "Biomedical_Dataset", "num_queries": 1, "llm_name": "nemotron"}
        self.observation.store.record("execution_start", input="CFTR")
        with self.assertRaisesRegex(ValueError, "native failure"):
            asyncio.run(agent.ainvoke("CFTR", context=context, config=self.observation.config()))
        self.observation.store.record("execution_error", error="native failure")
        evidence = self.evidence()
        wrapper = next(s for s in evidence.evidence["spans"] if s["name"] == "biomedical.native_workflow")
        self.assertEqual(wrapper["status"], "error")
        self.assertEqual(json.loads((self.folder / "otel-status.json").read_text())["unfinished_spans"], 0)


if __name__ == "__main__":
    unittest.main()
