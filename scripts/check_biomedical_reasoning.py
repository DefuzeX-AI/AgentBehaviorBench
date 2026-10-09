"""Probe the exact native streamed query-planning contract, without retries.

Print only protocol/JSON statistics, never credentials or reasoning text.
One hosted NVIDIA request may consume quota; this is not ABB acceptance.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys
from pathlib import Path
import time
import urllib.error
import urllib.request

from dotenv import dotenv_values
from langchain_core.utils.json import parse_json_markdown

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources/agents/41-biomedical-aiq-research-agent"
MODEL = "nvidia/nemotron-3-super-120b-a12b"
URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def native_prompt() -> str:
    """Read the source-owned prompt constant without importing the Agent."""
    source = UNIT / "agent/aira/src/aiq_aira/prompts.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "query_writer_instructions"
            for target in node.targets
        ):
            return ast.literal_eval(node.value).format(
                number_of_queries=1,
                topic="CFTR cystic fibrosis treatment",
                report_organization="Briefly summarize evidence and limitations. Do not perform virtual screening.",
            )
    raise ValueError("Native query prompt not found")


def contract_summary(content: str, finish_reason: str | None) -> dict:
    """Apply the native delimiter split and JSON parser to visible content only."""
    def valid_query_list(value):
        return isinstance(value, list) and len(value) == 1 and all(
            isinstance(item, dict) and all(
                isinstance(item.get(key), str) and item[key].strip()
                for key in ("query", "report_section", "rationale")
            ) for item in value
        )

    parts = content.split("</think>")
    queries = None
    if len(parts) >= 2:
        try:
            queries = parse_json_markdown(parts[1].strip())
        except (ValueError, TypeError):
            pass
    valid = valid_query_list(queries)
    # Diagnostic only: separate JSON syntax from native delimiter compatibility.
    # This does not accept missing delimiters or alter the native pass verdict.
    try:
        content_json_valid = valid_query_list(parse_json_markdown(content))
    except (ValueError, TypeError):
        content_json_valid = False
    return {
        "closing_think_in_content": len(parts) >= 2,
        "content_query_json_valid_without_delimiter": content_json_valid,
        "query_json_valid": valid,
        "query_count": len(queries) if isinstance(queries, list) else 0,
        "finish_reason": finish_reason,
        "native_query_contract_passed": bool(valid and finish_reason == "stop"),
    }


def list_models(key: str, timeout: float) -> dict:
    """GET the authenticated catalog; do not submit inference or print secrets."""
    request = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/models",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    summary = {"operation": "model_catalog", "catalog_verified": False}
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            summary["http"] = response.status
            payload = json.load(response)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("Unexpected catalog schema")
        names = sorted({row["id"] for row in rows if isinstance(row, dict)
                        and isinstance(row.get("id"), str)
                        and "nemotron" in row["id"].lower()
                        and not any(word in row["id"].lower() for word in ("embed", "rerank"))})
        summary.update(catalog_verified=True, candidate_models=names)
    except urllib.error.HTTPError as exc:
        summary["http"] = exc.code
    except Exception as exc:
        summary["error_type"] = type(exc).__name__
    return summary


def check(key: str, timeout: float, model: str = MODEL, *, adapt_reasoning: bool = False) -> dict:
    converter = client_parser = None
    if adapt_reasoning:
        # Use the exact interceptor adapter, not a second diagnostic implementation.
        sys.path.insert(0, str(ROOT / "agentbench/services/model-interceptor/src"))
        from model.thinking import ThinkingChatWire
        from defuzex_model_interceptor.transport.sse import SSEDecoder
        converter = ThinkingChatWire().stream()
        client_parser = SSEDecoder()
    body = json.dumps({
        "model": model, "temperature": 0.5, "max_tokens": 5000, "stream": True,
        "messages": [
            {"role": "system", "content": "detailed thinking on"},
            {"role": "user", "content": native_prompt()},
        ],
    }).encode()
    request = urllib.request.Request(URL, body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json", "Accept": "text/event-stream",
    })
    started = time.monotonic()
    summary = {"model": model, "native_query_contract_passed": False}
    try:
        content, adapted_content, reasoning_seen, finish_reason, usage = "", "", False, None, None
        with urllib.request.urlopen(request, timeout=timeout) as response:
            summary["http"] = response.status
            for line in response:
                if time.monotonic() - started > timeout:
                    raise TimeoutError("Native query deadline exceeded")
                if converter is not None:
                    forwarded = converter.feed(line)
                    for converted in (client_parser.feed(forwarded) if forwarded else []):
                        adapted_content += "".join(
                            (choice.get("delta") or {}).get("content") or ""
                            for choice in converted.get("choices", []))
                    if converter.parser.done:
                        break
                line = line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    if converter is None:
                        break
                    continue
                event = json.loads(value)
                if event.get("error"):
                    raise ValueError("Provider returned a stream error")
                if isinstance(event.get("usage"), dict):
                    usage = {k: v for k, v in event["usage"].items()
                             if k in ("prompt_tokens", "completion_tokens", "total_tokens")}
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    content += delta.get("content") or ""
                    reasoning_seen |= bool(delta.get("reasoning_content"))
                    finish_reason = choice.get("finish_reason") or finish_reason
        if converter is not None:
            client_parser.feed(converter.feed(b""))
        summary.update(contract_summary(content, finish_reason))
        summary["separate_reasoning_seen"] = reasoning_seen
        summary["usage"] = usage
        if adapt_reasoning:
            adapted = contract_summary(adapted_content, finish_reason)
            summary["response_adapter"] = ThinkingChatWire.response_adapter
            summary["adapted_query_contract_passed"] = adapted["native_query_contract_passed"]
            summary["adapted_query_count"] = adapted["query_count"]
    except urllib.error.HTTPError as exc:
        summary["http"] = exc.code
    except Exception as exc:
        # Exception text and raw responses may contain credentials/reasoning.
        summary["error_type"] = type(exc).__name__
    summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--list-models", action="store_true",
                        help="Query model catalog only; no inference request")
    parser.add_argument("--model", default=MODEL,
                        help="Candidate model ID; keeps the native prompt and parser contract")
    parser.add_argument("--adapt-reasoning", action="store_true",
                        help="Verify the explicit reasoning-content-to-inline interceptor adapter")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and positive")
    if not args.model.strip() or any(ch.isspace() for ch in args.model):
        parser.error("model must be a non-empty ID without whitespace")
    key = os.environ.get("NVIDIA_API_KEY") or dotenv_values(args.env_file).get("NVIDIA_API_KEY")
    if not key or not key.strip():
        parser.error("NVIDIA_API_KEY is missing")
    if args.list_models:
        print("Querying NVIDIA model catalog only; NO inference requests.", flush=True)
        summary = list_models(key.strip(), args.timeout)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary.get("catalog_verified") else 1
    print("Sending ONE native NVIDIA query-planning request (max_tokens=5000); no retries.", flush=True)
    summary = check(key.strip(), args.timeout, model=args.model, adapt_reasoning=args.adapt_reasoning)
    print(json.dumps(summary, ensure_ascii=False))
    passed = "adapted_query_contract_passed" if args.adapt_reasoning else "native_query_contract_passed"
    return 0 if summary.get(passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
