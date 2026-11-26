"""Run ABB's normal CLI with a declared HTTP User-Agent; preserve SDK bodies.

This host-only helper is not copied into the Agent image (validation/ is ignored).
It changes no Agent source, prompts, Judge limits, verdicts or SDK implementation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request
from urllib.parse import urlsplit

class Audit(urllib.request.BaseHandler):
    handler_order = 100
    def __init__(self, path=None, allowed_model=None):
        self.path = Path(path) if path else None
        self.allowed_model = allowed_model
    def https_request(self, request):
        if request.get_method() == "POST" and urlsplit(request.full_url).path.endswith("/chat/completions"):
            body = request.data or b""
            payload = json.loads(body)
            if self.allowed_model and payload.get("model") != self.allowed_model:
                raise ValueError("Host model differs from the approved selection")
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                parsed = urlsplit(request.full_url)
                record = {"event":"host_model_request", "timestamp":time.time(),
                          "host":parsed.hostname, "path":parsed.path,
                          "model":payload.get("model"), "max_tokens":payload.get("max_tokens"),
                          "body_sha256":hashlib.sha256(body).hexdigest()}
                with self.path.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(record, separators=(",", ":")) + "\n")
        return request
    http_request = https_request

def http_opener(user_agent="AgentBehaviorBench/0.1", audit_path=None, allowed_model=None, *handlers):
    if not user_agent.strip() or len(user_agent) > 256 or any(ord(c) < 32 or ord(c) > 126 for c in user_agent):
        raise ValueError("HTTP User-Agent must be printable ASCII")
    opener = urllib.request.build_opener(Audit(audit_path, allowed_model), *handlers)
    opener.addheaders = [("User-Agent", user_agent)]
    return opener

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--http-user-agent", default="AgentBehaviorBench/0.1")
    parser.add_argument("--http-audit", type=Path)
    parser.add_argument("--allowed-model")
    args, cli_args = parser.parse_known_args(argv)
    original = urllib.request._opener
    urllib.request.install_opener(http_opener(args.http_user_agent, args.http_audit, args.allowed_model))
    try:
        from agentbench.cli.main import cli
        return cli(cli_args)
    finally:
        urllib.request._opener = original

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
