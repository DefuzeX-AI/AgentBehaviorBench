"""Merge SDK environment names into a staged Agent manifest without losing settings."""

from copy import deepcopy
import json
import re

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


def extend_runtime_environment(source: str, names: tuple[str, ...], *, field='env_keys') -> str:
    """Return TOML retaining all Agent settings and adding unique runtime env keys.

    Args:
        source: Original manifest text, with an explicit runtime table.
        names: Environment variable names required by the SDK; never secret values.
    Returns:
        A semantically validated manifest with the merged environment list.
    Raises:
        ValueError when the existing list is invalid or cannot be safely located.
    """
    if field not in ('env_keys', 'worker_env_keys'):
        raise ValueError('Unsupported runtime environment field')
    original = tomllib.loads(source)
    runtime = original.get('runtime')
    if not isinstance(runtime, dict):
        raise ValueError('Manifest requires a runtime table')
    existing = runtime.get(field, [])
    if not isinstance(existing, list) or any(not isinstance(key, str) or not key.strip() for key in existing):
        raise ValueError('runtime.env_keys must be a list of non-empty variable names')
    expected = deepcopy(original)
    expected['runtime'][field] = list(dict.fromkeys([*existing, *names]))
    assignment = field + ' = ' + json.dumps(expected['runtime'][field])

    def matches(candidate):
        try:
            return tomllib.loads(candidate) == expected
        except tomllib.TOMLDecodeError:
            return False

    if field in runtime:
        # Parsing and full-document equality handle multiline arrays and prevent
        # changing an identically named key in a different table or string.
        for start in re.finditer(rf'''(?m)^[ \t]*(?:{field}|"{field}"|'{field}')\s*=''', source):
            for end in re.finditer(r'\n|\Z', source[start.end():]):
                boundary = start.end() + end.end()
                candidate = source[:start.start()] + assignment + '\n' + source[boundary:]
                if matches(candidate):
                    return candidate
    else:
        for header in re.finditer(r'''(?m)^[ \t]*\[\s*(?:runtime|"runtime"|'runtime')\s*\][ \t]*(?:#[^\n]*)?(?:\n|$)''', source):
            candidate = source[:header.end()].rstrip('\n') + '\n' + assignment + '\n' + source[header.end():]
            if matches(candidate):
                return candidate
    raise ValueError('Cannot safely merge SDK environment names into the runtime table')
