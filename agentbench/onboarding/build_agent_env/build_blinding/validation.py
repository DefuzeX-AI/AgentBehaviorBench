"""Check binding syntax and declared exports without importing untrusted code."""
import ast
from agentbench.runtime.agentcontainer.config import tomllib
from ..common.errors import BuildError


def validate_binding(content, session):
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ainvoke":
            if any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node)):
                raise BuildError("ainvoke must return an awaitable final result, not yield an async iterator; consume the native stream inside ainvoke")
    manifest = tomllib.loads(session.completed.get("agent.toml", ""))
    reference = manifest.get("adapter", {}).get("binding", "")
    if not reference:
        return
    filename, _, attribute = reference.rpartition(":")
    if "bindings/" + filename != session.current_path:
        return
    factory = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == attribute), None)
    if factory is None:
        raise BuildError("Binding must define the selected export as a synchronous factory function")
    positional = len(factory.args.posonlyargs) + len(factory.args.args)
    if positional > len(factory.args.defaults) or any(value is None for value in factory.args.kw_defaults):
        raise BuildError("Binding factory must be callable without arguments")
    if factory.decorator_list:
        raise BuildError("Binding factory must be undecorated so its zero-argument interface can be checked")
    if _yields(factory):
        raise BuildError("Binding factory must return an invoke-capable object, not a generator")


def _yields(node):
    """Inspect the factory body without attributing nested function yields to it."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.Yield, ast.YieldFrom)) or _yields(child):
            return True
    return False
