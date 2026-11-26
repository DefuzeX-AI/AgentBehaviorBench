"""Configure the native Jan ACP process using ABB's runtime model selection."""

import json
import os
from pathlib import Path


def main():
    names = ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise SystemExit("Missing ABB runtime settings: " + ", ".join(missing))
    model, base_url, api_key = (os.environ[name] for name in names)
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    config = (
        f"default_model = {quote(model)}\n"
        "[providers.abb]\n"
        f"api_key = {quote(api_key)}\n"
        f"base_url = {quote(base_url)}\n"
        f"models = [{quote(model)}]\n"
        'api_type = "openai"\n'
    )
    # Only the disposable container user's native config is written. In replace
    # mode the credential is ABB's injected placeholder, not the provider secret.
    directory = Path.home() / ".jan"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / "config.toml"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(config)
    os.execvp("jan", ["jan", "acp"])


if __name__ == "__main__":
    main()
