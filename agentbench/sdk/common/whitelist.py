"""Read SDK URL whitelists and render evaluation routes for agent.toml."""
import json
import re
from copy import deepcopy
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path
from urllib.parse import urlsplit


def load_whitelist(path: Path, extra_entries=()) -> list[dict]:
    """Load URL/method entries; only a trailing /* may match multiple paths.

    ``extra_entries`` use the same shape and validation and follow the file's
    entries; they carry routes that depend on run configuration.
    """
    entries = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(entries, list):
        raise ValueError(f'{path}: whitelist must be a JSON array')
    entries = [*entries, *extra_entries]
    routes = []
    for index, entry in enumerate(entries):
        label = f'{path}: whitelist entry {index + 1}'
        if not isinstance(entry, dict) or set(entry) != {'url', 'methods'}:
            raise ValueError(f'{label} must contain url and methods')
        url, methods = entry['url'], entry['methods']
        if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError(f'{label} requires a URL without whitespace')
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or '?' in url or '#' in url or '\\' in url
                or any(c in parsed.hostname for c in '*?[]')):
            raise ValueError(f'{label} requires an HTTP(S) URL without credentials, query or fragment')
        route_path = parsed.path or '/'
        literal_path = route_path[:-2] if route_path.endswith('/*') else route_path
        if route_path == '/*' or any(c in literal_path for c in '*?[]'):
            raise ValueError(f'{label} only permits a trailing /* below a specific path')
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)
        if not 1 <= port <= 65535:
            raise ValueError(f'{label} requires a port between 1 and 65535')
        if (not isinstance(methods, list) or not methods
                or any(not isinstance(method, str) or method not in
                       {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}
                       for method in methods)):
            raise ValueError(f'{label} requires explicit uppercase HTTP methods')
        routes.append({
            'purpose': 'evaluation',
            'host_patterns': [parsed.hostname],
            'ports': [port],
            'methods': methods,
            'path_patterns': [route_path],
        })
    return routes


def whitelist_toml(path: Path, extra_entries=()) -> str:
    """Serialize whitelist routes for appending to an evaluation manifest."""
    return ''.join(
        '\n[[llm_interception.tool_routes]]\n' + ''.join(
            f'{key} = {json.dumps(value, ensure_ascii=False)}\n'
            for key, value in route.items()
        )
        for route in load_whitelist(path, extra_entries)
    )


def append_whitelist(source: str, path: Path, extra_entries=()) -> str:
    """Append evaluation routes, including manifests with an explicit empty array.

    TOML forbids appending array-of-table entries to a previously assigned array.
    Remove only the empty declaration whose full parsed document matches the
    expected semantic change; preserve comments and all unrelated settings.
    """
    original = tomllib.loads(source)
    interception = original.get('llm_interception', {})
    if interception.get('tool_routes') == []:
        expected = deepcopy(original)
        del expected['llm_interception']['tool_routes']
        cleaned = None
        for start in re.finditer(r'''(?m)^[ \t]*(?:tool_routes|"tool_routes"|'tool_routes')\s*=''', source):
            for end in re.finditer(r'\n|\Z', source[start.end():]):
                boundary = start.end() + end.end()
                candidate = source[:start.start()] + source[boundary:]
                try:
                    matches = tomllib.loads(candidate) == expected
                except tomllib.TOMLDecodeError:
                    matches = False
                if matches:
                    cleaned = candidate
                    break
            if cleaned is not None:
                break
        if cleaned is None:
            raise ValueError('Cannot safely extend empty llm_interception.tool_routes')
        source = cleaned
    result = source + whitelist_toml(path, extra_entries)
    tomllib.loads(result)
    return result
