"""Map ABB model selection into native DotCraft configuration and launch ACP."""
import json
import os
from pathlib import Path
import subprocess
import sys


def configuration(source):
    required = ("ABB_AGENT_MODEL_PROVIDER", "ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY")
    if any(not source.get(key, "").strip() for key in required):
        raise ValueError("DotCraft requires runtime-selected provider, model, endpoint and credential")
    provider = source["ABB_AGENT_MODEL_PROVIDER"]
    return {"ProviderId": provider,
            "Providers": {provider: {"DisplayName": provider, "Protocol": "openai-chat-completions",
                                      "AuthMethod": "apiKey", "EndPoint": source["ABB_AGENT_MODEL_BASE_URL"],
                                      "ApiKey": "$DOTCRAFT_API_KEY"}},
            "ProviderPreferences": {provider: {"model": source["ABB_AGENT_MODEL"]}}}


def main():
    env = dict(os.environ)
    config = configuration(env)
    env["DOTCRAFT_API_KEY"] = env["ABB_AGENT_MODEL_API_KEY"]
    home = Path(env["HOME"])
    directory = home / ".craft"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.json"
    path.write_text(json.dumps(config) + "\n", encoding="utf-8")
    path.chmod(0o600)
    binary = "/opt/dotcraft/dotcraft"
    if not Path(".craft/config.json").exists():
        subprocess.run([binary, "setup", "--provider-mode", "skip"], env=env,
                       stdout=sys.stderr, stderr=sys.stderr, check=True)
    os.execve(binary, [binary, "acp"], env)


if __name__ == "__main__":
    main()
