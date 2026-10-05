"""Reject provably incompatible direct factories without executing source."""
import ast

from agentbench.sdk.contracts import SDKOnboardingInputs
from ...common.errors import BuildError
from ...openrouter_provider.context import safe_file


def validate_forwarding_input(factory, tree, manifest, session):
    """A text-only SDK cannot directly invoke a graph with a mapping state schema."""
    sdk = getattr(session, "sdk", None)
    if not isinstance(sdk, SDKOnboardingInputs) or sdk.onboarding_input_types() != ("text",):
        return
    if manifest["adapter"].get("input_key"):
        return
    returns = [node.value for node in factory.body if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0], ast.Call) or not isinstance(returns[0].func, ast.Name):
        return
    reference = returns[0].func.id
    imports = [*ast.walk(factory), *tree.body]
    imported = next(((node.module, alias.name) for node in imports
                     if isinstance(node, ast.ImportFrom) and not node.level
                     for alias in node.names if (alias.asname or alias.name) == reference), None)
    if imported is None or not imported[0]:
        return
    root = session.source.directory / "agent"
    native = _module(root, imported[0])
    if native is None:
        return
    definition = next((node for node in native.body if isinstance(node, ast.FunctionDef)
                       and node.name == imported[1]), None)
    if definition is None:
        return
    graph_names = {alias.asname or alias.name for node in native.body
                   if isinstance(node, ast.ImportFrom) and node.module == "langgraph.graph"
                   for alias in node.names if alias.name == "StateGraph"}
    for node in ast.walk(definition):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id not in graph_names:
            continue
        schema = node.args[0] if node.args else next((item.value for item in node.keywords
                                                    if item.arg == "state_schema"), None)
        if isinstance(schema, ast.Name) and _mapping_schema(root, native, schema.id):
            raise BuildError("SDK supplies text but the forwarding factory returns a mapping-state graph "
                             "without input conversion. The ABB worker does not run the upstream CLI. "
                             "Implement invoke that parses/validates the native problem text and reproduces "
                             "the public caller's initial state, writable paths and required resources; "
                             "do not claim the CLI performs those steps automatically.")


def _module(root, name):
    for base in ("", "src/"):
        for suffix in (".py", "/__init__.py"):
            path = safe_file(root, base + name.replace(".", "/") + suffix)
            if path is not None and path.stat().st_size <= 1024 * 1024:
                try:
                    return ast.parse(path.read_text(encoding="utf-8-sig"))
                except (UnicodeError, SyntaxError):
                    return None
    return None


def _mapping_schema(root, tree, name):
    declaration = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name), None)
    if declaration is not None:
        bases = {node.id for node in declaration.bases if isinstance(node, ast.Name)}
        mapping_bases = {alias.asname or alias.name for node in tree.body
                         if isinstance(node, ast.ImportFrom) and node.module in {"pydantic", "typing", "typing_extensions"}
                         for alias in node.names if alias.name in {"BaseModel", "TypedDict"}}
        return bool(bases & mapping_bases)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    imported = _module(root, node.module)
                    if imported is not None:
                        # Inspect only this class; never follow cyclic re-exports.
                        local = next((item for item in imported.body if isinstance(item, ast.ClassDef)
                                      and item.name == alias.name), None)
                        if local is not None:
                            return _mapping_schema(root, imported, alias.name)
    return False
