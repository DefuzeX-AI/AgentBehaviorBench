"""Compare explicit initialization with the public caller without running it."""
import ast

from ...common.errors import BuildError
from ...openrouter_provider.context import safe_file


def validate_native_initialization(tree, session):
    """Reject explicit empty runtime paths or forced source-conditional decisions."""
    issues = []
    for name in getattr(session.source, "files", ()):
        if not name.endswith('.py'):
            continue
        path = safe_file(session.source.directory / 'agent', name)
        if path is None or path.stat().st_size > 1024 * 1024:
            continue
        try:
            caller = ast.parse(path.read_text(encoding='utf-8-sig'))
        except (UnicodeError, SyntaxError):
            continue
        source_values = _dictionary_values(caller)
        for key, value in _dictionary_values(tree):
            native = [item for field, item in source_values if field == key]
            if key.endswith(('_dir', '_path')) and _is_none(value, tree):
                if any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
                       and item.func.id == 'str' and len(item.args) == 1
                       and isinstance(item.args[0], ast.Name) for item in native):
                    issues.append(f'{key} is explicitly empty but {name} supplies a runtime path. '
                                  'Create a container-writable run directory and preserve required resource setup; '
                                  'do not disable native file output or use a read-only source directory.')
            if isinstance(value, ast.Call):
                selected = _reference(value, tree)
                if selected is not None and any(isinstance(item, ast.IfExp)
                    and isinstance(item.body, ast.Call) and _reference(item.body, caller) == selected
                    and _same_boolean_choice(value, item.body)
                    for item in native):
                    issues.append(f'{key} unconditionally constructs {selected[1]}, but {name} makes '
                                  'that decision conditional. Preserve the native default and require an explicit '
                                  'input option for approval; never auto-approve human review to finish a benchmark.')
    if issues:
        raise BuildError('Native initialization mismatch: ' + '; '.join(dict.fromkeys(issues)))


def _dictionary_values(tree):
    return [(key.value, value) for node in ast.walk(tree) if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)]


def _same_boolean_choice(left, right):
    choices = {item.arg: item.value.value for item in right.keywords
               if isinstance(item.value, ast.Constant) and type(item.value.value) is bool}
    return any(isinstance(item.value, ast.Constant) and type(item.value.value) is bool
               and item.arg in choices and choices[item.arg] == item.value.value for item in left.keywords)


def _reference(call, tree):
    if not isinstance(call.func, ast.Name):
        return None
    return next(((node.module, alias.name) for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module and not node.level
                 for alias in node.names if (alias.asname or alias.name) == call.func.id), None)


def _is_none(value, tree):
    if isinstance(value, ast.Constant):
        return value.value is None
    if not isinstance(value, ast.Name):
        return False
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(node is value for node in ast.walk(function)):
            continue
        arguments = [*function.args.posonlyargs, *function.args.args]
        defaults = [None] * (len(arguments) - len(function.args.defaults)) + list(function.args.defaults)
        for index, (argument, default) in enumerate(zip(arguments, defaults)):
            if argument.arg != value.id or not isinstance(default, ast.Constant) or default.value is not None:
                continue
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == function.name]
            if calls and any(len(call.args) <= index and not any(keyword.arg in {value.id, None}
                             for keyword in call.keywords) for call in calls):
                return True
    return False
