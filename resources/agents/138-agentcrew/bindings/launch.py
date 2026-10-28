"""Launch pinned AgentCrew with native configuration and a dedicated ACP pipe."""
from __future__ import annotations

from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from urllib.parse import urlsplit


PROVIDER = "abb_runtime"
MODEL_KEYS = ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY")


def provider_config(environ):
    for name in MODEL_KEYS:
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    base = urlsplit(environ[MODEL_KEYS[1]])
    if (base.scheme != "https" or not base.hostname or base.username or base.password
            or base.query or base.fragment):
        raise ValueError("ABB_AGENT_MODEL_BASE_URL requires HTTPS without URL credentials or query")
    model = environ[MODEL_KEYS[0]]
    return {"name": PROVIDER, "type": "openai_compatible",
            "api_base_url": environ[MODEL_KEYS[1]], "api_key": environ[MODEL_KEYS[2]],
            "default_model_id": model, "available_models": [
                {"id": model, "provider": PROVIDER, "name": model,
                 "description": "ABB runtime-selected model", "default": True,
                 "capabilities": ["tool_use", "stream"]}]}


def prepare(directory, environ, defaults):
    """Create private per-process configuration without changing upstream source."""
    provider = provider_config(environ)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = directory / "config.json"
    config.write_text(json.dumps({"custom_llm_providers": [provider]}), encoding="utf-8")
    config.chmod(0o600)
    name, description, prompt = defaults
    # JSON basic strings are valid TOML strings, including embedded newlines/quotes.
    agents = directory / "agents.toml"
    agents.write_text("[[agents]]\n" + "\n".join(
        f"{key} = {json.dumps(value, ensure_ascii=False)}"
        for key, value in {"name": name, "description": description,
                           "system_prompt": prompt,
                           "tools": ["memory", "browser", "web_search", "code_analysis"]}.items()
    ) + "\n", encoding="utf-8")
    (directory / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
    return {"AGENTCREW_CONFIG_PATH": str(config), "SW_AGENTS_CONFIG": str(agents),
            "MCP_CONFIG_PATH": str(directory / "mcp.json"),
            "MEMORYDB_PATH": str(directory / "memorydb"),
            "AGENTCREW_PERSISTENCE_DIR": str(directory / "persistents"),
            "AGENTCREW_LOG_PATH": str(directory / "logs"),
            "AGENTCREW_DISABLE_GUI": "true", "AGENTCREW_DOCKER": "true",
            "AGENTCREW_PROVIDER": PROVIDER}


def reserve_protocol_output(protocol_output):
    """Keep native diagnostics off the wire, including writes directly to fd 1."""
    import acp
    from acp.core import DEFAULT_STDIO_BUFFER_LIMIT_BYTES
    from acp.stdio import stdio_streams

    native_run = acp.run_agent

    async def run_agent(agent, *args, **kwargs):
        # AgentCrew uses the SDK's default stdio form. Preserve its protocol flags.
        with redirect_stdout(protocol_output):
            reader, writer = await stdio_streams(limit=DEFAULT_STDIO_BUFFER_LIMIT_BYTES)
        await native_run(agent, writer, reader, *args, **kwargs)

    acp.run_agent = run_agent


def main():
    # Validate before importing native clients or writing credentials.
    provider_config(os.environ)
    with os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1) as protocol_output:
        sys.stdout.flush()
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        reserve_protocol_output(protocol_output)
        from AgentCrew.modules.agents.example import DEFAULT_NAME, DEFAULT_DESCRIPTION, DEFAULT_PROMPT

        with tempfile.TemporaryDirectory(prefix="abb-agentcrew-") as temporary:
            os.environ.update(prepare(Path(temporary), os.environ,
                                      (DEFAULT_NAME, DEFAULT_DESCRIPTION, DEFAULT_PROMPT)))
            from AgentCrew.main import cli_prod

            def terminate(signum, frame):
                raise SystemExit(128 + signum)

            signal.signal(signal.SIGTERM, terminate)
            # Invoke the actual CLI, including its setup and resource shutdown.
            # The native CLI's --provider choice lists built-ins only; its
            # AGENTCREW_PROVIDER resolver explicitly supports custom providers.
            sys.argv = ["agentcrew", "acp",
                        "--model-id", os.environ[MODEL_KEYS[0]], "--agent", DEFAULT_NAME]
            cli_prod()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError):
        # Native errors can contain request data; do not echo exception contents.
        print("AgentCrew launcher configuration failed", file=sys.stderr)
        raise SystemExit(1)
