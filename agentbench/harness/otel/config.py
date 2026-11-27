"""Read the same trace selection at build and launch time."""
from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from .profiles import PROFILES


@dataclass(frozen=True)
class CaptureConfig:
    profile: str = "unconfigured"
    protocol: str = "http/protobuf"
    enable_env: dict = field(default_factory=dict)
    endpoint_env: str = ""
    file: str = ""
    reason: str = ""
    file_format: str = "otlp-json"
    capture_content: bool = True


def parse_config(manifest):
    table = manifest.get("otel", {})
    if not isinstance(table, dict):
        raise ValueError("otel must be a table")
    if manifest.get("framework") == "langgraph" and table.get("profile") in (None, "python-auto"):
        table = {**table, "profile": "langfuse-auto"}
    config = CaptureConfig(**table)
    if type(config.capture_content) is not bool:
        raise ValueError("otel.capture_content must be a boolean")
    if config.profile not in PROFILES:
        raise ValueError(f"Unknown OTel profile: {config.profile}")
    if config.protocol not in ("http/protobuf", "http/json", "grpc"):
        raise ValueError("Unknown OTLP trace protocol")
    if config.profile in ("openclaw", "opensoul", "python-auto", "langfuse-auto") and config.protocol != "http/protobuf":
        raise ValueError(f"{config.profile} exports OTLP traces using http/protobuf")
    if not isinstance(config.enable_env, dict) or not all(
        isinstance(k, str) and k.isidentifier() and k.isupper() and isinstance(v, str)
        for k, v in config.enable_env.items()
    ):
        raise ValueError("otel.enable_env must contain string environment settings")
    if config.endpoint_env and not (config.endpoint_env.isidentifier() and config.endpoint_env.isupper()):
        raise ValueError("Invalid OTel endpoint variable")
    if config.file_format not in ("otlp-json", "llxprt-jsonl", "whip-session"):
        raise ValueError("Unknown Agent trace file format")
    if config.profile == "file-export":
        if not config.file or Path(config.file).is_absolute() or ".." in Path(config.file).parts:
            raise ValueError("otel.file must be a relative output path")
    return config


def read_config(root):
    with (Path(root) / "agent.toml").open("rb") as stream:
        return parse_config(tomllib.load(stream))
