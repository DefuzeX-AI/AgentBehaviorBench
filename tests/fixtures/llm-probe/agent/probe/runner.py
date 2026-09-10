"""Execute selected drivers, recording actual client text and first-token latency."""
import asyncio
import time
from .registry import load_cases

DEFAULT_MODELS = {"openai": "gpt-4o-mini", "google": "gemini-2.5-flash",
                  "anthropic": "claude-sonnet-4-20250514", "ollama": "qwen2.5:0.5b",
                  "deepseek": "deepseek-chat", "qwen": "qwen-turbo"}

async def run_suite(value):
    cases = load_cases()
    selected = value.get("cases") or list(cases)
    unknown = set(selected) - cases.keys()
    if unknown:
        raise ValueError(f"Unknown probe cases: {sorted(unknown)}")
    if len(selected) > 40 or len(set(selected)) != len(selected):
        raise ValueError("Select at most 40 unique cases")
    settings = {"models": DEFAULT_MODELS | value.get("models", {}),
                "prompt": value.get("prompt", "Reply with exactly: 测试 OK")}
    results = []
    for name in selected:
        case = cases[name]
        started, first, chunks = time.monotonic(), None, []
        def receive(text):
            nonlocal first
            if not isinstance(text, str):
                raise TypeError("Probe expected text")
            if text:
                if first is None:
                    first = time.monotonic()
                chunks.append(text)
        row = {"case": name, "streaming": case.streaming}
        try:
            await asyncio.wait_for(case.run(settings, receive), timeout=35)
            if not chunks:
                raise AssertionError("Original client returned no text")
            row.update(status="passed", text="".join(chunks), chunks=len(chunks))
        except Exception as exc:
            row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        row.update(first_text_ms=None if first is None else round((first-started)*1000, 3),
                   total_ms=round((time.monotonic()-started)*1000, 3))
        results.append(row)
    return {"matrix": results, "passed": sum(r["status"] == "passed" for r in results),
            "failed": sum(r["status"] == "failed" for r in results)}

def create_graph():
    from langchain_core.runnables import RunnableLambda
    return RunnableLambda(run_suite, name="interception.probe")

