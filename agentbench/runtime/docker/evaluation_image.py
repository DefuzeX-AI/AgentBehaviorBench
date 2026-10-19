"""Stage an evaluation controller image without changing the original Agent unit."""

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import tempfile
from types import SimpleNamespace

from agentbench.observe.timing import span
from .source_links import materialize_file_links
from .worker_build import agent_build_ignore

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


# Install into the interpreter the controller actually runs. A uv-created venv
# may omit pip, but ensurepip can bootstrap it without a network request.
SDK_INSTALL = (
    'RUN interpreter="$(command -v python)" '
    '|| { echo "ABB evaluation overlay: no python on the image PATH" >&2; exit 1; }; '
    'python -m pip --version >/dev/null 2>&1 '
    '|| python -m ensurepip --default-pip >/dev/null '
    '|| { echo "ABB evaluation overlay: $interpreter has no pip module and no ensurepip;'
    ' install pip into that interpreter in the Agent Dockerfile" >&2; exit 1; }; '
    'python -m pip --isolated install --upgrade --no-cache-dir '
    '--index-url https://pypi.org/simple '
    '-r /opt/abb-sdk/requirements.txt\n'
)


@contextmanager
def evaluation_image(agent, *, requirements, worker_module, control=None, deadline=None,
                     worker_environment=(), manifest_transform=None, image_environment=(),
                     required_files=(), optional_files=(), install_command=SDK_INSTALL):
    """Yield an isolated Agent descriptor with the requested controller installed.

    Plugins supply their dependency file, module entry point and configuration.
    ``manifest_transform`` receives the staged TOML after the launch/environment
    changes. ``image_environment`` contains Docker ENV assignments without secrets.
    Required and existing optional files/directories are copied from the staged
    unit to the same relative path under /opt/agent. Required COPY inputs are
    checked by the image build, preserving the Agent's normal build validation.
    """
    requirements = Path(requirements)

    def check():
        if control is not None:
            control.check()
        if deadline is not None:
            deadline.check()

    def checked_copy(source, target):
        check()
        with open(source, 'rb') as incoming, open(target, 'wb') as outgoing:
            while chunk := incoming.read(1024 * 1024):
                check()
                outgoing.write(chunk)
        shutil.copystat(source, target)
        return target

    check()
    if not requirements.is_file() or requirements.is_symlink():
        raise ValueError('Evaluation requirements.txt is missing or linked')
    with tempfile.TemporaryDirectory(prefix='abb-evaluation-') as temporary:
        with span('Prepare evaluation overlay', kind='preparation'):
            root = Path(temporary) / 'agent-unit'
            shutil.copytree(agent.path, root, ignore=agent_build_ignore(agent.path), symlinks=True,
                            copy_function=checked_copy)
            materialize_file_links(root, check)
            if any(p.is_symlink() for p in root.rglob('*')):
                raise ValueError('Agent source must not contain symlinks')
            staged_sdk = root / '.abb-sdk'
            staged_sdk.mkdir()
            shutil.copy2(requirements, staged_sdk / 'requirements.txt')
            if any(p.is_symlink() for p in root.rglob('*')):
                raise ValueError('Evaluation build must not contain symlinks')
            source = (root / 'agent.toml').read_text(encoding='utf-8')
            controller = ("import runpy,sys; sys.path.insert(0, '/opt/abb-sdk-runtime'); "
                          + f"runpy.run_module({worker_module!r}, run_name='__main__')")
            source, count = re.subn(r'(?m)^argv = .*$',
                                   lambda _: 'argv = ' + json.dumps(['python', '-I', '-c', controller]), source)
            if count != 1:
                raise ValueError('Expected one explicit launch.argv')
            if worker_environment:
                source = extend_runtime_environment(source, tuple(worker_environment), field='worker_env_keys')
            if manifest_transform is not None:
                source = manifest_transform(source)
            (root / 'agent.toml').write_text(source, encoding='utf-8')
            dockerfile = root / 'Dockerfile'
            original = dockerfile.read_text(encoding='utf-8')
            users = re.findall(r'(?im)^USER\s+(.+)$', original)
            if not users or users[-1].strip() in ('root', '0'):
                raise ValueError('Evaluation requires an explicit non-root image USER')
            copies = ''
            selected = dict.fromkeys((*required_files, *(name for name in optional_files if (root / name).exists())))
            for name in selected:
                relative = Path(name).as_posix()
                suffix = '/' if (root / name).is_dir() else ''
                copies += f'COPY {relative}{suffix} /opt/agent/{relative}{suffix}\n'
            environment = ''.join(f'ENV {assignment}\n' for assignment in image_environment)
            dockerfile.write_text(original + '\n' + environment + 'USER root\nCOPY .abb-sdk/ /opt/abb-sdk/\n'
                                 + install_command + 'COPY .abb-runtime/ /opt/abb-sdk-runtime/\n' + copies
                                 + 'USER ' + users[-1] + '\n', encoding='utf-8')
            check()
        yield SimpleNamespace(path=root, agent_id=agent.agent_id, framework=agent.framework)


def extend_runtime_environment(source: str, names: tuple[str, ...], *, field='env_keys') -> str:
    """Add environment names while preserving all other parsed Agent settings."""
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
        # Full-document equality handles multiline arrays without changing an
        # identically named key in another table or string.
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
