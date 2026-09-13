"""Protect the adapter dependency rules and public plugin extension paths."""
import ast
from importlib.util import resolve_name
from pathlib import Path
from types import SimpleNamespace

import pytest

import defuzex_model_interceptor
import model
from defuzex_model_interceptor import registry
from defuzex_model_interceptor.error import TargetRoutingError
from defuzex_model_interceptor.targets.openrouter import OpenRouterTarget
from defuzex_model_interceptor.config import Route, Target
from model.native import NativeJsonWire


def imports(path, root, package):
    relative = path.relative_to(root).with_suffix("").parts
    context = ".".join((package, *relative[:-1]))
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            yield resolve_name("." * node.level + name, context) if node.level else name


def test_adapters_and_shared_modules_have_no_reverse_runtime_dependencies():
    core = Path(defuzex_model_interceptor.__file__).parent
    models = Path(model.__file__).parent
    public = "defuzex_model_interceptor"
    allowed = tuple(f"{public}.{name}" for name in ("contracts", "config", "error", "security", "transport"))
    for path in models.rglob("*.py"):
        for dependency in imports(path, models, "model"):
            if dependency == public or dependency.startswith(public + "."):
                assert dependency.startswith(allowed), (path, dependency)
    for area in ("contracts.py", "error", "transport", "security", "targets", "observation", "routing"):
        folder = core / area
        paths = [folder] if folder.is_file() else folder.rglob("*.py")
        for path in paths:
            for dependency in imports(path, core, public):
                assert not dependency.startswith(("model", f"{public}.proxy", f"{public}.registry")), (path, dependency)
                if area == "error":
                    assert not dependency.startswith(public) or dependency.startswith(f"{public}.error"), (path, dependency)


def test_package_initializers_do_not_hide_implementation():
    for root in (Path(defuzex_model_interceptor.__file__).parent, Path(model.__file__).parent):
        for path in root.rglob("__init__.py"):
            definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            assert not any(isinstance(node, definitions) for node in ast.walk(ast.parse(path.read_text()))), path


@pytest.mark.parametrize("export_kind", ["instance", "class", "factory"])
def test_authentication_plugins_support_instances_classes_and_factories(monkeypatch, export_kind):
    class CustomAuth:
        name = "custom-auth"

        def authorize(self, headers, *, temporary_token, upstream_secret):
            headers["checked"] = temporary_token

    exports = {"instance": CustomAuth(), "class": CustomAuth, "factory": lambda: CustomAuth()}
    entry = SimpleNamespace(load=lambda: exports[export_kind])
    monkeypatch.setattr(registry, "entry_points", lambda *, group: [entry] if group == registry.AUTH_GROUP else [])
    plugins = registry.load_authentication()
    headers = {}
    plugins["custom-auth"].authorize(headers, temporary_token="temporary", upstream_secret="upstream")
    assert headers == {"checked": "temporary"}
    assert {"bearer-token", "google-api-key", "anthropic-api-key"} <= plugins.keys()


def test_target_uses_injected_wire_factory_without_plugin_discovery(monkeypatch):
    def unexpected_discovery():
        raise AssertionError("Target must not discover adapters itself")

    monkeypatch.setattr(registry, "load_wires", unexpected_discovery)
    target = OpenRouterTarget({"custom": lambda: NativeJsonWire("/custom")})
    route = Route("r", ("source.test",), (443,), ("POST",), ("/model",), "custom", "key")
    request = SimpleNamespace(content=b'{"model":"source","messages":[]}', headers={})
    result = target.prepare_request(request, route=route,
        target=Target("test", "openrouter", "https://target.test/v1", "target-model", {}))
    assert request.host == "target.test"
    assert request.path == "/v1/custom"
    assert result.source_model == "source" and result.target_model == "target-model"
    with pytest.raises(TargetRoutingError, match="does not support"):
        OpenRouterTarget({}).prepare_request(request, route=route,
            target=Target("test", "openrouter", "https://target.test", "m", {}))
