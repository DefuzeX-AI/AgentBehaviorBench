"""ABB boundary for NVIDIA's native Biomedical AI-Q research workflow.

The upstream package registers an ``ai_researcher`` NeMo Agent Toolkit
workflow. That workflow constructs and invokes the project's two native
LangGraphs: query planning, followed by RAG/web research, report drafting,
reflection, optional virtual screening and finalization. This binding uses the
same ``WorkflowBuilder`` lifecycle as the upstream tests; it does not recreate
the graphs or replace their nodes.

ABB/KUMA supplies text, while the native workflow expects a JSON string. Plain
text becomes the native ``topic`` plus the source-confirmed Biomedical_Dataset
defaults declared in ``[adapter.context]``. A complete JSON object is also
accepted for explicit native arguments. The native end-to-end function returns
its final report as text; the binding exposes it under ``report`` for
``output_key``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

__all__ = ["create_graph"]

_FIELDS = {
    "topic",
    "report_organization",
    "search_web",
    "rag_collection",
    "num_queries",
    "llm_name",
}


def _native_input(value: Any, context: Mapping[str, Any] | None = None) -> str:
    """Map plain topic text or explicit JSON to the native JSON string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Input must be non-empty topic text or a JSON object")
    if value.lstrip().startswith("{"):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON-form input is invalid") from exc
    else:
        defaults = dict(context or {})
        expected_defaults = _FIELDS - {"topic"}
        if set(defaults) != expected_defaults:
            raise ValueError("Plain-text input requires the complete adapter context")
        payload = {"topic": value.strip(), **defaults}
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")
    missing = _FIELDS - set(payload)
    extra = set(payload) - _FIELDS
    if missing or extra:
        details = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if extra:
            details.append("unsupported: " + ", ".join(sorted(extra)))
        raise ValueError("Input must contain exactly the native fields (" + "; ".join(details) + ")")
    for name in ("topic", "report_organization", "rag_collection"):
        if not isinstance(payload[name], str) or not payload[name].strip():
            raise ValueError(f"{name} must be a non-empty string")
    if payload["llm_name"] != "nemotron":
        raise ValueError("llm_name must be 'nemotron', the configured reasoning model")
    if not isinstance(payload["search_web"], bool):
        raise ValueError("search_web must be a boolean")
    count = payload["num_queries"]
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
        raise ValueError("num_queries must be an integer from 1 through 10")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "agent" / "aira" / "configs" / "hosted-config.yml"


def _native_config() -> Mapping[str, Any]:
    """Load the upstream hosted-NIM config and apply only its RAG deployment address."""
    import yaml

    with _config_path().open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    rag_url = os.environ.get(
        "AIRA_RAG_URL", "http://host.docker.internal:8081/v1"
    ).strip()
    config["functions"]["generate_summary"]["rag_url"] = rag_url
    return config


class _SecretFilter(logging.Filter):
    """Redact optional tool credentials from native log records.

    The pinned upstream virtual-screening helper logs ``NVIDIA_API_KEY``. ABB
    must never place a credential in container logs or Trace artifacts, so the
    boundary installs a narrow value-based filter without changing Agent logic.
    """

    def __init__(self) -> None:
        super().__init__()
        self._values = tuple(
            value
            for name in ("NVIDIA_API_KEY", "RAG_API_KEY", "TAVILY_API_KEY")
            if (value := os.environ.get(name))
        )

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._values:
            return True
        message = record.getMessage()
        for value in self._values:
            message = message.replace(value, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def _install_secret_filter() -> None:
    root = logging.getLogger()
    marker = "_abb_biomedical_secret_filter"
    if getattr(root, marker, False):
        return
    redactor = _SecretFilter()
    previous_factory = logging.getLogRecordFactory()

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        redactor.filter(record)
        return record

    # The factory also covers handlers that libraries install after graph
    # construction. Existing handlers retain a filter as defense in depth.
    logging.setLogRecordFactory(redacting_factory)
    for handler in root.handlers:
        handler.addFilter(redactor)
    logging.getLogger("aiq_aira").addFilter(redactor)
    setattr(root, marker, True)


class BiomedicalAIQResearchAgent:
    """One-shot handle around the upstream ``ai_researcher`` workflow."""

    def __init__(self) -> None:
        self._closed = False
        _install_secret_filter()

    async def ainvoke(
        self,
        value: Any,
        config: Any = None,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, str]:
        """Run the complete native workflow and return its report.

        The Toolkit runner has no RunnableConfig argument. A public RunnableLambda
        establishes LangChain's inherited callback context around the unchanged
        runner, so the two native graphs can inherit ABB's observer without
        injecting callbacks or execution settings into their business state.
        """
        if self._closed:
            raise RuntimeError("Biomedical AI-Q binding is closed")
        input_message = _native_input(value, context)
        if config is not None and config.get("callbacks"):
            from langchain_core.runnables import RunnableLambda

            # Carry observation only, not an outer recursion limit/configurable
            # map that could override the native graph's own configuration.
            report = await RunnableLambda(
                self._run_native, name="biomedical.native_workflow"
            ).ainvoke(input_message, config={"callbacks": config["callbacks"]})
        else:
            report = await self._run_native(input_message)
        if not isinstance(report, str) or not report.strip():
            raise RuntimeError("Native Biomedical AI-Q workflow returned no final report")
        return {"report": report}

    async def _run_native(self, input_message: str) -> str:
        """Own the original Toolkit lifecycle without reconstructing its graphs."""

        # Registration imports mirror the upstream tests. They register the
        # project's functions, OpenAI-compatible LLM and FastAPI front end with
        # NeMo Agent Toolkit before WorkflowBuilder resolves hosted-config.yml.
        from aiq.builder.workflow_builder import WorkflowBuilder
        from aiq.data_models.config import AIQConfig
        from aiq.front_ends.fastapi.register import register_fastapi_front_end  # noqa: F401
        from aiq.llm import register as llm_register  # noqa: F401
        from aiq.llm.openai_llm import openai_llm  # noqa: F401
        from aiq_aira import register as aira_register  # noqa: F401
        from aiq_aira.functions import artifact_qa, generate_queries, generate_summary  # noqa: F401

        parsed = AIQConfig.parse_obj(_native_config())
        async with WorkflowBuilder.from_config(config=parsed) as builder:
            # ai_researcher is config.workflow, not a named config.functions
            # entry. build(entry_function=...) calls get_function() and would
            # fail because that name is absent from the function registry.
            workflow = builder.build()
            async with workflow.run(input_message) as runner:
                report = await runner.result()
        return report

    def invoke(
        self,
        value: Any,
        config: Any = None,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, str]:
        """Synchronous ABB entrypoint; async callers should use ``ainvoke``."""
        return asyncio.run(self.ainvoke(value, config=config, context=context, **kwargs))

    def close(self) -> None:
        self._closed = True


def create_graph() -> BiomedicalAIQResearchAgent:
    """Return a fresh synchronous zero-argument native-workflow wrapper."""
    return BiomedicalAIQResearchAgent()
