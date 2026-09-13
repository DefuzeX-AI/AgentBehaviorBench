"""Actual transparent network test in an isolated Docker network namespace.

Root owns the proxy and controlled TLS upstream. The original client Agent runs
as UID 10001 with temporary credentials; only the trusted proxy can reach upstream.
No real model key, model call, or client monkey-patching is used here.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
from upstream import start, TEXT
from defuzex_model_interceptor.proxy.netfilter import configure_netfilter
import defuzex_model_interceptor

def main():
    root = Path("/workspace")
    fixture = root / "tests/fixtures/llm-probe"
    directory = Path(tempfile.mkdtemp(prefix="abb-lab-"))
    directory.chmod(0o755)
    server, ca, upstream = start(directory)
    manifest = tomllib.loads((fixture / "agent.toml").read_text())["llm_interception"]
    credentials, env = [], dict(os.environ)
    for spec in manifest["credentials"]:
        token, secret = directory / (spec["id"] + ".token"), directory / (spec["id"] + ".secret")
        token.write_text("lab-temporary")
        secret.write_text("lab-upstream-secret")
        token.chmod(0o600)
        secret.chmod(0o600)
        credentials.append({"id": spec["id"], "auth_plugin": spec["auth_plugin"],
                            "token_file": str(token), "secret_file": str(secret)})
        env[spec["agent_env"]] = "lab-temporary"
    config = directory / "config.json"
    config.write_text(json.dumps({"agent_id": "probe-lab", "max_trace_bytes": 262144, "credentials": credentials,
        "routes": manifest["routes"], "target": {"provider_id": "controlled", "target_plugin": "openrouter",
        "base_url": "https://127.0.0.1:8443/api/v1", "model": "lab/target"}}))
    config.chmod(0o600)
    os.environ["DEFUZEX_INTERCEPTOR_CONFIG"] = str(config)
    configure_netfilter()
    log_path = directory / "proxy.log"
    proxy = None
    try:
        with log_path.open("w") as log:
            proxy = subprocess.Popen(["mitmdump", "--quiet", "--mode", "transparent",
                "--listen-host", "0.0.0.0", "--listen-port", "8080", "--set", f"confdir={directory}/ca",
                "--set", "connection_strategy=lazy", "--set", "upstream_cert=false", "--set", "rawtcp=false",
                "--set", f"ssl_verify_upstream_trusted_ca={ca}", "--scripts",
                str(Path(defuzex_model_interceptor.__file__).parent / "proxy" / "loader.py")], stdout=log, stderr=subprocess.STDOUT)
            for _ in range(100):
                if proxy.poll() is not None:
                    raise RuntimeError(log_path.read_text())
                if '"event": "interceptor_ready"' in log_path.read_text():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Proxy startup timeout")
            certificate = str(directory / "ca/mitmproxy-ca-cert.pem")
            env.update(SSL_CERT_FILE=certificate, REQUESTS_CA_BUNDLE=certificate,
                       GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=certificate, PYTHONDONTWRITEBYTECODE="1")
            settings = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
            child = subprocess.run([sys.executable, str(fixture / "agent/main.py"), json.dumps(settings)],
                        user=10001, group=10001, extra_groups=[], env=env, capture_output=True, text=True, timeout=1400)
            lines = child.stdout.strip().split("\n")
            result = json.loads(lines[-1]) if lines and lines[-1] else {"failed": 1, "matrix": [], "error": child.stderr}
            time.sleep(0.3)
            events = [json.loads(line[len("DEFUZEX_TRACE "):]) for line in log_path.read_text().split("\n")
                      if line.startswith("DEFUZEX_TRACE ")]
            requests = [e for e in events if e["event"] == "llm_request"]
            responses = [e for e in events if e["event"] == "llm_response"]
            for row in result["matrix"]:
                if row["status"] == "passed":
                    assert row["text"] == TEXT, row
                    if row["streaming"]:
                        assert row["total_ms"] - row["first_text_ms"] > 100, ("Buffered stream", row)
            result["evidence"] = {"requests": len(requests), "responses": len(responses),
                "upstream_calls": len(upstream), "errors": [e for e in events if e["event"] == "llm_error"],
                "grpc_requests": sum(e.get("source_transport") == "grpc" for e in requests),
                "all_upstream_auth_replaced": all(r["auth_replaced"] for r in upstream),
                "all_upstream_target_model": all(r["payload"]["model"] == "lab/target" for r in upstream)}
            if not result["failed"]:
                assert len(requests) == len(responses) == len(upstream) == len(result["matrix"]), result["evidence"]
                assert {e["call_id"] for e in requests} == {e["call_id"] for e in responses}
                assert not result["evidence"]["errors"]
            if settings.get("faults"):
                fault = subprocess.run([sys.executable, str(Path(__file__).with_name("faults.py"))],
                    user=10001, group=10001, extra_groups=[], env=env, capture_output=True, text=True, timeout=60)
                result["faults"] = json.loads(fault.stdout.strip().split("\n")[-1])
                result["failed"] += result["faults"]["failed"]
                fault_events = [json.loads(line[len("DEFUZEX_TRACE "):]) for line in log_path.read_text().split("\n")
                                if line.startswith("DEFUZEX_TRACE ")][len(events):]
                events.extend(fault_events)
                result["faults"]["trace_errors"] = sum(e["event"] == "llm_error" for e in fault_events)
            output = Path("/artifacts")
            output.mkdir(exist_ok=True)
            (output / "controlled.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
            (output / "controlled.trace.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events)+"\n")
            (output / "controlled.proxy.log").write_text(log_path.read_text())
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            return bool(result["failed"])
    finally:
        if proxy is not None:
            proxy.terminate()
            proxy.wait(timeout=10)
        server.shutdown()

if __name__ == "__main__":
    raise SystemExit(main())
