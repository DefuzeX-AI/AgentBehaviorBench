"""Exercise native GPT report-chat through KUMA/worker using offline transports.

No GPTResearcher, FastAPI endpoint, ReportStore, embedding or chat function is
replaced. A local HTTP server supplies model completions; only NCBI requests are
redirected to deterministic external-service fixtures. The ASGI transport spy
records calls and reads the native report through its public GET endpoint.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4


REPORT = "# ALPHA evidence\n\nThe ALPHA cohort enrolled 42 participants. [Source](https://www.ncbi.nlm.nih.gov/pmc/articles/123456/)."
ARTICLE = """<pmc-articleset><article><front><article-meta>
<title-group><article-title>ALPHA cohort evidence</article-title></title-group>
<abstract><p>The ALPHA cohort enrolled 42 participants.</p></abstract>
</article-meta></front><body><sec><title>Results</title>
<p>In the ALPHA cohort, the investigators followed 42 adult participants.</p>
</sec></body></article></pmc-articleset>"""


class OfflineServices:
    """Deterministic model/search I/O; no state from outside a model request."""
    def __init__(self):
        self.models = []
        self.searches = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                assert self.path == "/v1/chat/completions", self.path
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                answer, phase = owner.complete(payload)
                owner.models.append({"request": payload, "answer": answer, "phase": phase})
                if answer is None:
                    body = b'{"error":{"message":"Injected offline model request failure","type":"invalid_request_error","code":"offline_failure"}}'
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                base = {"id": "offline-" + str(len(owner.models)), "created": int(time.time()),
                        "model": "gpt-4.1-mini"}
                if payload.get("stream"):
                    chunks = [dict(base, object="chat.completion.chunk", choices=[
                        {"index": 0, "delta": {"role": "assistant", "content": answer}, "finish_reason": None}]),
                        dict(base, object="chat.completion.chunk", choices=[
                            {"index": 0, "delta": {}, "finish_reason": "stop"}]),
                        dict(base, object="chat.completion.chunk", choices=[], usage={
                            "prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17})]
                    body = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                            + "data: [DONE]\n\n").encode()
                    content_type = "text/event-stream"
                else:
                    body = json.dumps(dict(base, object="chat.completion", choices=[
                        {"index": 0, "message": {"role": "assistant", "content": answer},
                         "finish_reason": "stop"}], usage={
                             "prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17})).encode()
                    content_type = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def complete(self, payload):
        messages = payload["messages"]
        text = "\n".join(str(message.get("content", "")) for message in messages)
        if "This is a chat about a research report" in text:
            if messages[-1].get("content") == "Trigger offline transport failure.":
                return None, "report-chat-failure"
            # The answer depends ONLY on messages the real native app supplied.
            remembered = "unset"
            for message in messages:
                content = message.get("content", "")
                if message["role"] == "user" and content.startswith("Remember my label "):
                    remembered = content.removeprefix("Remember my label ").rstrip(".")
            return "Remembered label: " + remembered, "report-chat"
        if "agent_role_prompt" in text and '"server"' in text:
            return json.dumps({"server": "Biomedical Researcher",
                               "agent_role_prompt": "Research biomedical literature."}), "agent-selection"
        if "search queries" in text.lower():
            return '["ALPHA cohort clinical evidence"]', "research-planning"
        return REPORT, "report-writing"

    def ncbi_send(self, request, **kwargs):
        from requests import Response
        parsed = urlsplit(request.url)
        assert parsed.hostname == "eutils.ncbi.nlm.nih.gov", f"Unexpected external request: {parsed.hostname}"
        self.searches.append({"method": request.method, "path": parsed.path, "query": parsed.query})
        response = Response()
        response.status_code = 200
        response.url = request.url
        response.request = request
        if parsed.path.endswith("esearch.fcgi"):
            response._content = b'{"esearchresult":{"idlist":["123456"]}}'
            response.headers["Content-Type"] = "application/json"
        else:
            assert parsed.path.endswith("efetch.fcgi"), parsed.path
            response._content = ARTICLE.encode()
            response.headers["Content-Type"] = "application/xml"
        return response

    @contextmanager
    def installed(self):
        self.thread.start()
        environ = {"OPENAI_BASE_URL": f"http://127.0.0.1:{self.server.server_port}/v1",
                   "OPENAI_API_KEY": "offline-placeholder", "TAVILY_API_KEY": ""}
        def send(session, request, **kwargs):
            return self.ncbi_send(request, **kwargs)
        try:
            with patch.dict(os.environ, environ), patch("requests.sessions.Session.send", send):
                yield self
        finally:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)


class NativeAPISpy:
    """Read-only observation of original ASGI endpoint requests and responses."""
    def __init__(self):
        self.calls = []
        self.store_paths = set()

    @contextmanager
    def installed(self):
        import httpx
        original = httpx.ASGITransport.handle_async_request
        owner = self

        async def handle(transport, request):
            response = await original(transport, request)
            await response.aread()
            if request.method != "POST" or not request.url.path.startswith("/api/reports"):
                return response
            body = json.loads(request.content)
            result = response.json()
            row = {"path": request.url.path, "input": body, "response": result,
                   "status": response.status_code, "app_identity": id(transport.app)}
            report_id = result.get("id") or (request.url.path.split("/")[3]
                if request.url.path.endswith("/chat") else None)
            if report_id:
                get_request = httpx.Request("GET", f"http://native-app/api/reports/{report_id}")
                stored = await original(transport, get_request)
                await stored.aread()
                row["stored_report"] = stored.json()["report"]
            # Inspect the original endpoint's store ownership without changing
            # it. Storage contents themselves are read via the public API above.
            for route in transport.app.routes:
                if getattr(route, "path", None) == "/api/reports/{research_id}":
                    native_store = route.endpoint.__globals__["report_store"]
                    owner.store_paths.add(str(native_store._path))
            owner.calls.append(row)
            return response

        with patch.object(httpx.ASGITransport, "handle_async_request", handle):
            yield self


def write_case_unit(source, root):
    """Preserve current Agent files while allowing SDK Case files in its repo."""
    root.mkdir(parents=True)
    (root / "agent").mkdir()
    for child in (source / "agent").iterdir():
        destination = root / "agent" / child.name
        if child.is_dir():
            destination.symlink_to(child, target_is_directory=True)
        else:
            shutil.copyfile(child, destination)
    shutil.copyfile(source / "agent.toml", root / "agent.toml")
    shutil.copytree(source / "bindings", root / "bindings")
    shutil.copytree(source / "evaluation", root / "evaluation")


async def execute_case(root, output, inputs, expected):
    from kuma import create_run as real_create_run
    from agentbench.sdk.common.case_identity import case_content_sha256
    from agentbench.sdk.plugin.kuma.compatibility import run_case
    from agentbench.sdk.plugin.kuma.worker import execute

    output.mkdir(parents=True)
    case = {"case_id": "native-chat-" + uuid4().hex, "input_type": "text", "inputs": [
        {"input_id": f"turn-{number}", "payload_type": "text", "payload": value}
        for number, value in enumerate(inputs, 1)]}
    prepared = real_create_run(repo_path=root / "agent", agent_profile_path=root / "requirement.md",
        case_provider=lambda context: case, judge=False, allow_local=False, track_files=False,
        max_steps=len(inputs))
    path = root / "agent" / (case["case_id"] + ".json")
    try:
        prepared.save_case(path)
        identity = {"case_id": prepared.case_id, "content_sha256": case_content_sha256(run_case(prepared))}
    finally:
        prepared.cancel()

    def judge(context):
        actual = [item.submission.output for item in context.history]
        assert actual == expected, actual
        assert [item.test_input.payload for item in context.history] == inputs
        return {"status": "pass", "summary": "Offline Judge verified native report and memory delivery; no model quality claim.", "issues": []}

    def create_run(**options):
        return real_create_run(**options, judge_provider=judge)

    with patch("kuma.create_run", side_effect=create_run), patch.dict(os.environ, {
        "KUMA_API_KEY": "offline-provider-placeholder"}):
        code = await execute(root, output, {"case_artifact": str(path), "expected_case": identity,
                                           "max_steps": len(inputs)})
    return code


async def main():
    source, workspace, output = Path("/opt/agent"), Path("/tmp/native-chat-acceptance"), Path("/artifacts")
    root = workspace / "unit"
    write_case_unit(source, root)
    cases = [("five-turns", ["Research the ALPHA cohort.", "Remember my label BLUE.", "What is my label?",
                            "Remember my label GREEN.", "What is my label?"],
              [REPORT, "Remembered label: BLUE", "Remembered label: BLUE", "Remembered label: GREEN", "Remembered label: GREEN"], 0),
             ("fresh-case", ["Research the ALPHA cohort.", "What is my label?", "Remember my label ORANGE."],
              [REPORT, "Remembered label: unset", "Remembered label: ORANGE"], 0),
             ("model-failure", ["Research the ALPHA cohort.", "Remember my label VIOLET.", "Trigger offline transport failure."],
              [REPORT, "Remembered label: VIOLET", None], 1)]
    checks = []
    with OfflineServices().installed() as services, NativeAPISpy().installed() as api:
        # Exercise native local report RAG, including actual embedding work;
        # this probe does not replace the constructor used by the real routes.
        sys.path.insert(0, str(source / "agent/backend"))
        from chat.chat import ChatAgentWithMemory
        probe = ChatAgentWithMemory(REPORT)
        assert probe.config.embedding_model == "/opt/models/all-MiniLM-L6-v2"
        assert probe.retriever is not None and probe.tavily_client is None
        assert probe.retriever.invoke("ALPHA cohort")[0].page_content == REPORT
        assert len(probe.embedding.embed_query("ALPHA cohort")) == 384
        del probe
        for name, inputs, expected, expected_code in cases:
            folder = output / name
            api_start, models_start, searches_start = len(api.calls), len(services.models), len(services.searches)
            paths_before = set(api.store_paths)
            code = await execute_case(root, folder, inputs, expected)
            calls = api.calls[api_start:]
            models = services.models[models_start:]
            searches = services.searches[searches_start:]
            (folder / "native-api.json").write_text(json.dumps(calls, indent=2))
            (folder / "model-requests.json").write_text(json.dumps(models, indent=2))
            (folder / "search-requests.json").write_text(json.dumps(searches, indent=2))
            assert code == expected_code, (folder / "manifest.json").read_text()
            post_report, *chat_calls = calls
            assert post_report["path"] == "/api/reports"
            assert post_report["input"]["answer"] == REPORT
            assert [call["input"] for call in chat_calls] == [
                {"role": "user", "content": value} for value in inputs[1:]]
            successful_chats = len(inputs) - 1 - expected_code
            assert len(chat_calls[-1]["stored_report"]["chatMessages"]) == 2 * successful_chats
            assert len({call["app_identity"] for call in calls}) == 1
            assert {model["phase"] for model in models} >= {"agent-selection", "research-planning", "report-writing", "report-chat"}
            assert searches and any(request["path"].endswith("efetch.fcgi") for request in searches)
            for model in models:
                if model["phase"] == "report-writing":
                    assert "42" in json.dumps(model["request"]["messages"])
                    assert inputs[0] in json.dumps(model["request"]["messages"])
            normal_chats = [model for model in models if model["phase"] == "report-chat"]
            expected_history = []
            for index, model in enumerate(normal_chats, 1):
                assert model["request"]["messages"][1:] == [*expected_history,
                    {"role": "user", "content": inputs[index]}]
                expected_history.extend([{"role": "user", "content": inputs[index]},
                                         {"role": "assistant", "content": expected[index]}])
            requests = [json.loads(path.read_text()) for path in sorted((folder / "inputs").glob("*/request.json"))]
            assert [request["input"] for request in requests] == inputs
            session = json.loads((folder / "session.json").read_text())
            assert session["adapter_initializations"] == 1 and session["closed"] is True
            store_paths = api.store_paths - paths_before
            assert store_paths and all(not Path(path).exists() for path in store_paths)
            framework = [json.loads(line) for path in (folder / "inputs").glob("*/framework.jsonl")
                         for line in path.read_text().split("\n") if line.strip()]
            (folder / "framework-events.json").write_text(json.dumps(framework, indent=2))
            llm_starts = [event["data"] for event in framework
                          if event["event"] == "span_start" and event["data"].get("kind") == "llm"]
            assert len(llm_starts) == len(models)
            terminal_ids = {event["data"]["span_id"] for event in framework
                            if event["event"] in {"span_end", "span_error"}}
            assert all(event["span_id"] in terminal_ids for event in llm_starts)
            checks.append({"name": name, "session_closed": session["closed"], "storage_removed": True,
                           "store_paths": sorted(store_paths), "app_identity": calls[0]["app_identity"],
                           "turns": len(inputs), "native_chat_turns": len(chat_calls), "exit_code": code,
                           "observed_model_spans": len(llm_starts)})
        assert checks[0]["app_identity"] != checks[1]["app_identity"]
        overlap = await overlapping_sessions(root, output / "overlapping", api)
    (output / "acceptance.json").write_text(json.dumps({"status": "passed", "network": "none",
        "app_function_replacements": [], "external_service_doubles": ["OpenAI HTTP", "NCBI HTTP"],
        "local_embeddings": True, "embedding_dimensions": 384, "cases": checks,
        "overlapping_sessions": overlap, "cwd": str(Path.cwd()),
        "docker_policy": {"memory": "1g", "tmpfs_size": "64m", "cpus": 1}}, indent=2))
    print(json.dumps({"status": "passed", "cases": [case["name"] for case in checks]}))


async def overlapping_sessions(root, output, api):
    """Keep two native app owners alive; closing one must not affect the other."""
    from agentbench.runtime.agentcontainer.session import AgentSession
    from agentbench.runtime.agentcontainer.worker import execute
    from opentelemetry.sdk.trace import TracerProvider
    output.mkdir()
    first, second = AgentSession(), AgentSession()
    provider = TracerProvider()
    calls_start, paths_start = len(api.calls), set(api.store_paths)

    async def turn(session, name, index, value):
        folder = output / f"{name}-{index}"
        folder.mkdir()
        request = folder / "request.json"
        request.write_text(json.dumps({"schema": "abb.invocation.v1", "run_id": uuid4().hex,
            "session_id": name, "agent_id": "gpt-researcher", "framework": "langgraph", "input": value}))
        code = await execute(root, request, folder, provider=provider, session=session)
        data = json.loads((folder / "result.json").read_text())
        return code, data

    try:
        assert (await turn(first, "live-a", 1, "Research the ALPHA cohort."))[0] == 0
        assert (await turn(first, "live-a", 2, "Remember my label BLUE."))[1]["output"] == "Remembered label: BLUE"
        assert (await turn(second, "live-b", 1, "Research the ALPHA cohort."))[0] == 0
        assert (await turn(second, "live-b", 2, "What is my label?"))[1]["output"] == "Remembered label: unset"
        assert (await turn(second, "live-b", 3, "Remember my label ORANGE."))[1]["output"] == "Remembered label: ORANGE"
        store_paths = api.store_paths - paths_start
        assert len(store_paths) == 2 and all(Path(path).is_file() for path in store_paths)
        await first.aclose()
        assert sum(Path(path).exists() for path in store_paths) == 1
        assert (await turn(second, "live-b", 4, "What is my label?"))[1]["output"] == "Remembered label: ORANGE"
        assert (await turn(first, "live-a", 3, "What is my label?"))[0] == 1
    finally:
        await first.aclose()
        await second.aclose()
        provider.shutdown()
    assert all(not Path(path).exists() for path in api.store_paths - paths_start)
    (output / "native-api.json").write_text(json.dumps(api.calls[calls_start:], indent=2))
    return {"survivor_retained_memory": True, "closed_session_rejected": True,
            "app_stores": 2, "both_storage_paths_removed": True}


if __name__ == "__main__":
    asyncio.run(main())
