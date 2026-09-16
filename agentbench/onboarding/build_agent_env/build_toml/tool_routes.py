"""Resolve known SDK calls to narrow routes without importing Agent code.

Only complete supplied files, explicit imported constructors, unambiguous client
assignments and observed calls are considered. Custom endpoints/kwargs disable
inference for that client. Unknown providers still require model/user evidence.
"""
import ast
import json
from pathlib import Path

CATALOG = Path(__file__).parent / "assets/tool-providers.json"


def network_evidence(context):
    catalog = json.loads(CATALOG.read_text())
    results = []
    for file in context.get("files", []):
        if not file["path"].endswith(".py") or file.get("truncated"):
            continue
        try:
            tree = ast.parse(file["content"])
        except SyntaxError:
            continue
        aliases = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and not node.level:
                aliases.update({item.asname or item.name: f"{node.module}.{item.name}" for item in node.names})
        # Class scopes keep identically named attributes on different classes apart.
        scopes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        scopes.append(ast.Module(body=[n for n in tree.body if not isinstance(n, ast.ClassDef)], type_ignores=[]))
        for scope in scopes:
            assignments = {}
            for node in ast.walk(scope):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
                for target in targets:
                    assignments.setdefault(ast.dump(target, include_attributes=False).replace("Store()", "Load()"), []).append(node.value)
            for receiver, values in assignments.items():
                if len(values) != 1 or not isinstance(values[0], ast.Call):
                    continue
                call = values[0]
                symbol = aliases.get(call.func.id) if isinstance(call.func, ast.Name) else None
                for provider, spec in catalog.items():
                    if symbol not in spec["constructors"] or call.args or any(
                        keyword.arg not in spec["safe_constructor_keywords"] for keyword in call.keywords
                    ):
                        continue
                    methods = sorted({node.func.attr for node in ast.walk(scope)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and ast.dump(node.func.value, include_attributes=False) == receiver
                        and node.func.attr in spec["operations"]})
                    if methods:
                        results.append({"provider": provider, "source": file["path"], "operations": methods,
                            "documentation": spec["documentation"], "route": {
                                **{key: spec[key] for key in ("host_patterns", "ports", "methods")},
                                "path_patterns": [spec["operations"][method] for method in methods]}})
    return results


def complete_routes(existing, evidence):
    """Fill an omitted route list only; never overwrite explicit endpoint choices."""
    if existing:
        return existing
    routes = {}
    for item in evidence:
        route = item["route"]
        key = json.dumps({name: route[name] for name in ("host_patterns", "ports", "methods")}, sort_keys=True)
        merged = routes.setdefault(key, {**route, "path_patterns": []})
        merged["path_patterns"] = sorted(set(merged["path_patterns"]) | set(route["path_patterns"]))
    return list(routes.values())
