"""Opt-in Docker conformance runner. --live explicitly permits model charges."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests/fixtures/llm-probe"

def command(*args):
    return subprocess.run(["docker", *map(str, args)], check=True, capture_output=True, text=True)

def controlled(output, settings, skip_build):
    if not skip_build:
        print("Building interceptor and original-client lab images...", flush=True)
        command("build", "-t", "abb-interceptor:protocol-validation", REPO / "services/model-interceptor")
        command("build", "-t", "abb-protocol-lab:validation", "-f", REPO / "tests/acceptance/interception/Dockerfile", FIXTURE)
    network = "abb-protocol-lab-" + uuid4().hex[:12]
    name = network + "-clients"
    command("network", "create", "--internal", network)
    try:
        args = ["run", "--rm", "--name", name, "--network", network, "--read-only",
                "--cap-drop=ALL", "--cap-add=NET_ADMIN", "--cap-add=NET_RAW",
                "--cap-add=SETUID", "--cap-add=SETGID", "--security-opt=no-new-privileges",
                "--tmpfs=/tmp:rw,nosuid,size=128m", "--memory=1g", "--pids-limit=256",
                "--env", "PYTHONPATH=/workspace:/workspace/services/model-interceptor/src"]
        for host in ("api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
                     "api.deepseek.com", "dashscope.aliyuncs.com"):
            args += ["--add-host", f"{host}:127.0.0.2"]
        # Never mount the workspace root or .env into an Agent.
        for relative in ("agentbench", "services/model-interceptor/src", "tests/acceptance/interception", "tests/fixtures/llm-probe"):
            args += ["--mount", f"type=bind,source={REPO / relative},target=/workspace/{relative},readonly"]
        args += ["--mount", f"type=bind,source={output},target=/artifacts",
                 "abb-protocol-lab:validation", json.dumps(settings)]
        process = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=1500)
        (output / "lab.stdout.log").write_text(process.stdout)
        (output / "lab.stderr.log").write_text(process.stderr)
        if process.returncode:
            print(process.stdout[-6000:] or process.stderr[-6000:])
        path = output / "controlled.json"
        return json.loads(path.read_text()) if path.exists() else {"failed": 1, "error": process.stderr[-6000:]}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        command("network", "rm", network)

def live(output, settings, args):
    from dotenv import dotenv_values
    from agentbench.observe.store import TraceStore, atomic_json
    from agentbench.runtime.docker.runtime import DockerRuntime
    from agentbench.runtime.agentcontainer.invocation import invoke_once
    from agentbench.runtime.interception import OpenRouterProvider, StaticInterceptorImageProvider
    environment = {k: v for k, v in dotenv_values(args.env_file).items() if v is not None} | dict(os.environ)
    if not environment.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is required for --live")
    runtime = DockerRuntime(environ=environment, model_provider=OpenRouterProvider(model=args.model),
        interceptor_image_provider=StaticInterceptorImageProvider(args.interceptor_image) if args.interceptor_image else None,
        trace_sink=TraceStore(output / "interceptor.jsonl", output.name, source="interceptor"),
        artifact_root=output, run_id=output.name)
    agent = SimpleNamespace(agent_id="llm-interception-probe", framework="langgraph", path=FIXTURE)
    try:
        invocation = invoke_once(runtime, agent, settings)
        result = invocation.raw_output
        rows = [json.loads(line)["data"] for line in (output / "interceptor.jsonl").read_text().split("\n") if line]
        requests = [r for r in rows if "source_model" in r]
        if len(requests) != len(result["matrix"]):
            raise AssertionError("Probe case count does not equal intercepted request count")
        result["evidence"] = {"requests": len(requests), "target_model": requests[0]["model"],
                              "source_models": sorted({str(r["source_model"]) for r in requests})}
    except Exception as exc:
        # Worker output and diagnostics survive strict trace validation failures.
        result = {"failed": 1, "error": f"{type(exc).__name__}: {exc}"}
    atomic_json(output / "live.json", result)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--controlled", action="store_true", help="No paid calls; isolated TLS upstream")
    mode.add_argument("--live", action="store_true", help="Use .env key; incurs model charges")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--cases", help="Comma-separated case names; default all")
    parser.add_argument("--source-model", action="append", default=[], metavar="PROVIDER=MODEL")
    parser.add_argument("--model", help="OpenRouter target model; otherwise OPENROUTER_MODEL")
    parser.add_argument("--env-file", type=Path, default=REPO / ".env")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-build", action="store_true", help="Reuse controlled lab images")
    parser.add_argument("--interceptor-image", help="Explicit live interceptor image")
    parser.add_argument("--faults", action="store_true", help="Controlled-only error/deadline/cancellation checks")
    args = parser.parse_args()
    sys.path.insert(0, str(FIXTURE / "agent"))
    from probe.registry import load_cases
    cases = load_cases()
    if args.list:
        print("\n".join(cases))
        return 0
    if not (args.controlled or args.live):
        parser.error("Select --controlled or --live explicitly")
    if args.faults and not args.controlled:
        parser.error("--faults requires --controlled; never send fault markers to real models")
    selected = args.cases.split(",") if args.cases else list(cases)
    if not selected or set(selected) - cases.keys() or len(selected) != len(set(selected)):
        parser.error("Cases must be unique names from --list")
    models = {}
    for item in args.source_model:
        key, separator, value = item.partition("=")
        if not separator or not value:
            parser.error("--source-model requires PROVIDER=MODEL")
        models[key] = value
    output = (args.output or REPO / "results/interception" / uuid4().hex).resolve()
    output.mkdir(parents=True, exist_ok=False)
    print(f"Evidence: {output}", flush=True)
    settings = {"cases": selected, "models": models, "faults": args.faults}
    try:
        result = live(output, settings, args) if args.live else controlled(output, settings, args.skip_build)
    except subprocess.CalledProcessError as exc:
        (output / "build-error.log").write_text((exc.stdout or "") + (exc.stderr or ""))
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(result.get("failed"))

if __name__ == "__main__":
    raise SystemExit(main())
