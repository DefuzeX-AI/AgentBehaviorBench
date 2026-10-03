"""Detect unconditional JSON decoding of text Cases without importing candidates.

This deliberately checks only straight-line invoke/helper calls. Conditional
format dispatch and unknown control flow are left to source review and execution.
"""
import ast

from agentbench.sdk.contracts import SDKOnboardingInputs
from ...common.errors import BuildError


def validate_plain_text(factory, tree, manifest, session):
    sdk = getattr(session, "sdk", None)
    if not isinstance(sdk, SDKOnboardingInputs) or sdk.onboarding_input_types() != ("text",):
        return
    if manifest["adapter"].get("input_key"):
        return
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for statement in factory.body:
        call = statement.value if isinstance(statement, ast.Return) else None
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        cls = classes.get(call.func.id)
        if cls is None:
            continue
        for method in cls.body:
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name in {"invoke", "ainvoke"}:
                args = [*method.args.posonlyargs, *method.args.args]
                if len(args) >= 2:
                    _check(method, args[1].arg, tree, functions, set())


def _check(function, parameter, tree, functions, visited):
    key = (function.name, parameter)
    if key in visited:
        return
    visited = {*visited, key}
    imports = [*tree.body, *function.body]
    modules = {alias.asname or alias.name for node in imports if isinstance(node, ast.Import)
               for alias in node.names if alias.name == "json"}
    decoders = {alias.asname or alias.name for node in imports
                if isinstance(node, ast.ImportFrom) and node.module == "json"
                for alias in node.names if alias.name == "loads"}

    def scan(statements):
        for statement in statements:
            if isinstance(statement, ast.Try):
                # A handler with a non-raising path may provide a text fallback.
                # Do not claim such a candidate is JSON-only without executing it.
                if not statement.handlers or all(_raises(handler) for handler in statement.handlers):
                    scan(statement.body)
                else:
                    return
            elif isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
                value = statement.value
                if value is None:
                    continue
                # Do not follow conditional expressions or nested lambdas.
                if any(isinstance(node, (ast.IfExp, ast.Lambda, ast.BoolOp)) for node in ast.walk(value)):
                    continue
                for call in (node for node in ast.walk(value) if isinstance(node, ast.Call)):
                    func = call.func
                    direct = isinstance(func, ast.Name) and func.id in decoders
                    qualified = (isinstance(func, ast.Attribute) and func.attr == "loads"
                                 and isinstance(func.value, ast.Name) and func.value.id in modules)
                    if (direct or qualified) and call.args and _input(call.args[0], parameter):
                        raise BuildError(
                            "SDK text Cases may contain plain text. This binding unconditionally "
                            "JSON-decodes the input and rejects it before native execution. Preserve "
                            "the complete text in a source-confirmed native problem/message field, "
                            "with native defaults; JSON may be an additional input format. If required "
                            "business fields cannot be derived truthfully, report needs_input."
                        )
                    helper = functions.get(func.id) if isinstance(func, ast.Name) else None
                    if helper is not None:
                        params = [*helper.args.posonlyargs, *helper.args.args]
                        for argument, param in zip(call.args, params):
                            if _input(argument, parameter):
                                _check(helper, param.arg, tree, functions, visited)
                targets = statement.targets if isinstance(statement, ast.Assign) else (
                    [statement.target] if isinstance(statement, ast.AnnAssign) else [])
                if any(isinstance(node, ast.Name) and node.id == parameter
                       for target in targets for node in ast.walk(target)):
                    # Subsequent decoding may operate on transformed input.
                    return
            elif isinstance(statement, ast.If):
                # An early return or assignment may implement format dispatch.
                # A type/empty-input guard containing only raise is harmless.
                if any(isinstance(node, (ast.Return, ast.Assign, ast.AnnAssign)) for node in ast.walk(statement)):
                    return
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                scan(statement.body)
            elif isinstance(statement, (ast.For, ast.While, ast.Match)):
                return
    scan(function.body)


def _input(node, parameter):
    return isinstance(node, ast.Name) and node.id == parameter


def _raises(handler):
    return any(isinstance(node, ast.Raise) for node in handler.body)
