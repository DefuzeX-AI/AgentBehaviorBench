"""Launch unchanged Octomind with a per-Case native configuration and ACP stdio."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import urlsplit


TEXT_MODEL_FIELDS = {
    'llm': ('model',),
    'index': ('contextual_model',),
    'search.reasoning': ('model',),
    'graphrag.llm': ('description_model', 'relationship_model'),
}


DEFAULT_MODEL_CACHE = Path('/opt/octomind-model-cache')
NATIVE_CONFIG = json.loads((Path(__file__).resolve().parent / 'local-models.json').read_text())['native_config']


def configure_template(template, overrides):
    """Change explicit native scalar fields; preserve every other template byte."""
    section = ''
    changed = set()
    output = []
    for line in template.splitlines(keepends=True):
        header = re.fullmatch(r'\s*\[([\w.]+)\]\s*', line)
        if header:
            section = header.group(1)
        assignment = re.match(r'^(\s*)(\w+)\s*=.*', line)
        if assignment and assignment.group(2) in overrides.get(section, {}):
            key = assignment.group(2)
            line = assignment.group(1) + key + ' = ' + json.dumps(overrides[section][key]) + '\n'
            changed.add((section, key))
        output.append(line)
    expected = {(section, key) for section, values in overrides.items() for key in values}
    if changed != expected:
        raise ValueError('Pinned native template does not expose all expected configuration fields')
    return ''.join(output)


def configure_octocode(template, profile):
    overrides = {section: {key: profile for key in keys} for section, keys in TEXT_MODEL_FIELDS.items()}
    for section, values in NATIVE_CONFIG['octocode'].items():
        overrides.setdefault(section, {}).update(values)
    return configure_template(template, overrides)


def seed_cache(source, target):
    """Isolate writable metadata; reference immutable shipped weights/packages.

    Private parent directories retain normal cache-miss downloads. Large public
    artifacts are not copied into the memory-accounted per-Case /tmp filesystem.
    """
    source, target = Path(source), Path(target)
    if not source.is_dir():
        raise ValueError('Bundled public dependency cache is required')
    target.mkdir(parents=True, exist_ok=False)
    for entry in source.iterdir():
        dest = target / entry.name
        if entry.is_dir() and entry.name == 'node_modules':
            dest.symlink_to(entry.resolve(), target_is_directory=True)
        elif entry.is_dir():
            seed_cache(entry, dest)
        elif entry.suffix == '.onnx' or 'content-v2' in entry.parts:
            dest.symlink_to(entry.resolve())
        else:
            shutil.copy2(entry, dest)


def prepare(environ, home, *, unit=Path('/opt/agent'), tap=Path('/opt/octomind-tap'),
            npm_cache=Path('/opt/octomind-npm-cache'), model_cache=None):
    """Configure native model profiles, including inherited subprocess profiles."""
    for name in ('ABB_AGENT_MODEL_API_KEY', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL'):
        if not environ.get(name, '').strip():
            raise ValueError(name + ' is required')
    base = environ['ABB_AGENT_MODEL_BASE_URL'].strip().rstrip('/')
    url = urlsplit(base)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c.isspace() for c in base)):
        raise ValueError('ABB_AGENT_MODEL_BASE_URL must be an HTTPS base URL without credentials, query or fragment')
    model = environ['ABB_AGENT_MODEL'].strip()
    if any(ord(c) < 32 for c in model):
        raise ValueError('ABB_AGENT_MODEL must not contain control characters')
    profile = 'openrouter:' + model
    home = Path(home)
    config = home / 'octomind/config'
    config.mkdir(parents=True, exist_ok=False)
    # Preserve the upstream template verbatim. A separate native TOML overlay
    # also reaches delegated ACP processes, unlike process-only CLI overrides.
    shutil.copyfile(unit / 'agent/config-templates/default.toml', config / 'config.toml')
    overlay = '\n'.join(
        '[' + section + ']\nname = ' + json.dumps(profile)
        for section in ('model', 'supervisor.model', 'compression.model')
    ) + '\n'
    (config / 'zz-abb-model.toml').write_text(overlay)
    # Native sidecar configuration is inherited by all delegated ACP processes.
    # Explicit retrieval-model fields use the documented supported local preset.
    # Native feature flags, prompts, guardrails and tools remain unchanged.
    defaults = unit / 'bootstrap/defaults'
    code_config = home / 'octocode/config.toml'
    code_config.parent.mkdir(parents=True)
    code_config.write_text(configure_octocode((defaults / 'octocode.toml').read_text(), profile))
    brain_config = home / 'octobrain/config.toml'
    brain_config.parent.mkdir(parents=True)
    brain_config.write_text(configure_template((defaults / 'octobrain.toml').read_text(), NATIVE_CONFIG['octobrain']))
    seed_cache(model_cache or DEFAULT_MODEL_CACHE, home / '.cache/octolib/huggingface')
    # Native npx resolves versioned package metadata even for a global install.
    # Seed a private writable cache; prefer hits, but keep normal cache-miss
    # downloads available. The exact upstream MCP command remains unchanged.
    npm_home = home / '.npm'
    if npm_cache.is_dir():
        seed_cache(npm_cache, npm_home)
    tap_link = home / 'octomind/taps/muvon/octomind-tap'
    tap_link.parent.mkdir(parents=True)
    tap_link.symlink_to(tap, target_is_directory=True)
    child = dict(environ)
    child.update({
        'HOME': str(home),
        'OCTOMIND_DATA_DIR': str(home / 'octomind'),
        'OCTOMIND_CONFIG_PATH': str(config / 'config.toml'),
        'OCTOCODE_CONFIG_PATH': str(code_config),
        'OCTOBRAIN_CONFIG_PATH': str(brain_config),
        'OPENROUTER_API_KEY': environ['ABB_AGENT_MODEL_API_KEY'],
        'OPENROUTER_API_URL': base + '/chat/completions',
        'OCTOMIND_TELEMETRY': '0',
        'DO_NOT_TRACK': '1',
        'TOKIO_WORKER_THREADS': '2',
        'npm_config_cache': str(npm_home),
        'npm_config_prefer_offline': 'true',
        'npm_config_update_notifier': 'false',
    })
    # No alternate credential can select a default cloud account accidentally.
    for name in ('OCTOHUB_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
                 'DEEPSEEK_API_KEY', 'OPENCODE_API_KEY',
                 'OPENAI_OAUTH_ACCESS_TOKEN', 'ANTHROPIC_OAUTH_ACCESS_TOKEN'):
        child.pop(name, None)
    for name, suffix in (('XDG_CONFIG_HOME', '.config'), ('XDG_DATA_HOME', '.local/share'),
                         ('XDG_CACHE_HOME', '.cache'), ('XDG_STATE_HOME', '.local/state')):
        child[name] = str(home / suffix)
    return ['/usr/local/bin/octomind', 'acp', 'developer:general', '--model', profile], child


def main():
    home = Path(tempfile.mkdtemp(prefix='abb-octomind-'))
    try:
        command, child = prepare(dict(os.environ), home)
        from model_transport import start_transport
        child['OPENROUTER_API_URL'] = start_transport() + '/chat/completions'
        child['NO_PROXY'] = ','.join(filter(None, [child.get('NO_PROXY'), '127.0.0.1', 'localhost']))
    except (OSError, ValueError):
        print('Octomind launch configuration is invalid; inspect the required ABB model fields and installation.', file=sys.stderr)
        return 1
    # ACP bytes, tools, permission checks and process signals stay native.
    os.execvpe(command[0], command, child)


if __name__ == '__main__':
    raise SystemExit(main())
