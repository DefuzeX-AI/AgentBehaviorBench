"""Bind the pinned upstream built-in agent to ABB's runtime-selected model."""

from pathlib import Path

import yaml


def bind_model(upstream, settings):
    if upstream["agents"]["root"]["model"] != "smart" or "smart" not in upstream["models"]:
        raise ValueError("The upstream built-in model layout changed; review this integration")
    upstream["models"]["smart"] = settings["smart"]
    return upstream


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    upstream = yaml.safe_load((directory / "upstream-default.yaml").read_text(encoding="utf-8"))
    settings = yaml.safe_load((directory / "config.yaml").read_text(encoding="utf-8"))
    config = bind_model(upstream, settings)
    (directory / "agent.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
