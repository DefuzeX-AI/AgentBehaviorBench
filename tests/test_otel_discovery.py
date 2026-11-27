"""Select an Agent's own OTLP exporter when declared, else its runtime's instrumentor."""
import json

import pytest

from agentbench.harness.otel.config import parse_config
from agentbench.onboarding.discovery import discover_otel

LAUNCHER = {"command": ["python", "/opt/agent/bootstrap/launch.py"]}
BINDING = {"binding": "bindings/graph.py:make_graph"}
PACKAGE = {"name": "agent", "bin": {"agent": "dist/cli.js"}}
INDIRECT = "module agent\nrequire go.opentelemetry.io/otel/exporters/otlp/otlptrace v1.30.0 // indirect\n"


def source(tmp_path, files):
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return tmp_path


def pyproject(*dependencies, extra=""):
    return f'[project]\nname="agent"\ndependencies={json.dumps(list(dependencies))}\n{extra}'


@pytest.mark.parametrize("framework, adapter, files, profile, evidence", [
    # An in-process graph is always Python; only a declared exporter makes it native.
    ("langgraph", BINDING, {"pyproject.toml": pyproject("langgraph")}, "langfuse-auto", None),
    ("langgraph", BINDING, {"pyproject.toml": pyproject("langgraph", "opentelemetry-exporter-otlp-proto-http>=1")},
     "native-otlp", "pyproject.toml"),
    ("langgraph", BINDING, {"requirements.txt": "langgraph\nopentelemetry_exporter_otlp==1.30\n"},
     "native-otlp", "requirements.txt"),
    ("langgraph", BINDING, {"pyproject.toml": pyproject(
        "langgraph", extra='[project.optional-dependencies]\notel=["opentelemetry-exporter-otlp"]\n')}, "langfuse-auto", None),
    ("langgraph", BINDING, {"package.json": PACKAGE, "backend/pyproject.toml": pyproject("opentelemetry-exporter-otlp")},
     "native-otlp", "backend/pyproject.toml"),
    # An ACP launcher is a Python wrapper; the source's build file names the real runtime.
    ("acp", LAUNCHER, {"package.json": PACKAGE}, "node-auto", None),
    ("acp", LAUNCHER, {"package.json": {**PACKAGE, "dependencies": {"@opentelemetry/sdk-node": "^0.57"}}},
     "native-otlp", "package.json"),
    ("acp", LAUNCHER, {"package.json": {**PACKAGE, "devDependencies": {"@opentelemetry/sdk-node": "^0.57"}}},
     "node-auto", None),
    ("acp", LAUNCHER, {"package.json": {**PACKAGE, "dependencies": {"@opentelemetry/api": "^1"}}}, "node-auto", None),
    ("acp", LAUNCHER, {"package.json": PACKAGE, "bun.lock": "{}"}, "unsupported", "bun executable"),
    ("acp", LAUNCHER, {"package.json": {**PACKAGE, "engines": {"bun": ">=1.4", "node": ">=22"}}},
     "unsupported", "bun executable"),
    # One level below the root, a library or front end is not the Agent.
    ("acp", LAUNCHER, {"sdk/package.json": {"name": "libagent"}}, "unconfigured", "No build file"),
    ("acp", LAUNCHER, {"docs/requirements.txt": "mkdocs\n"}, "unconfigured", "No build file"),
    ("acp", LAUNCHER, {"cli/pyproject.toml": pyproject("langgraph", extra='[project.scripts]\nagent="a:b"\n')},
     "python-auto", None),
    ("acp", LAUNCHER, {"rust/Cargo.toml": "[package]\n", "web/package.json": {"name": "web"}},
     "unsupported", "rust executable"),
    ("acp", LAUNCHER, {"pom.xml": "<project/>"}, "java-auto", None),
    ("acp", LAUNCHER, {"pyproject.toml": pyproject("langchain-core")}, "python-auto", None),
    ("acp", LAUNCHER, {"pyproject.toml": pyproject("httpx")}, "python-auto", "LangChain only"),
    ("acp", LAUNCHER, {"Cargo.toml": '[package]\nname="agent"\n'}, "unsupported", "rust executable"),
    ("acp", LAUNCHER, {"Cargo.toml": '[dependencies]\nopentelemetry-otlp = "0.27"\n'}, "native-otlp", "Cargo.toml"),
    ("acp", LAUNCHER, {"go.mod": INDIRECT}, "unsupported", "go executable"),
    ("acp", LAUNCHER, {"go.mod": INDIRECT.replace(" // indirect", "")}, "native-otlp", "go.mod"),
    # A compiled executable precedes the package.json that may only distribute it.
    ("acp", LAUNCHER, {"Cargo.toml": "[package]\n", "package.json": PACKAGE}, "unsupported", "also contains node"),
    ("acp", LAUNCHER, {"cli/package.json": PACKAGE, "docs/readme.md": ""}, "node-auto", None),
    ("acp", LAUNCHER, {"README.md": ""}, "unconfigured", "No build file"),
    # A direct runtime executable identifies the target without any build file.
    ("acp", {"command": ["node", "dist/cli.js"]}, {}, "node-auto", None),
])
def test_profile_follows_declared_exporter_then_runtime(tmp_path, framework, adapter, files, profile, evidence):
    selected = discover_otel(adapter, source(tmp_path, files), framework)
    assert selected["profile"] == profile
    assert (evidence in selected["reason"]) if evidence else "reason" not in selected
    assert parse_config({"otel": selected}).profile == profile


def test_known_product_keeps_its_enable_switch(tmp_path):
    selected = discover_otel({"command": ["copilot", "--acp"]}, tmp_path, "acp")
    assert selected == {"profile": "native-otlp", "enable_env": {"COPILOT_OTEL_ENABLED": "true"}}


def test_unreadable_declarations_never_select_native(tmp_path):
    root = source(tmp_path, {"package.json": "[1, 2", "pyproject.toml": "not = [toml"})
    assert discover_otel(LAUNCHER, root, "acp")["profile"] == "node-auto"
    assert discover_otel(BINDING, root, "langgraph") == {"profile": "langfuse-auto"}
