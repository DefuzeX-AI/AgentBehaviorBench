"""Install source-injected worker dependencies in the image's Python environment."""
import re


def stage_runtime_dependencies(context, dockerfile):
    source = dockerfile.read_text()
    users = re.findall(r'(?im)^USER\s+(.+)$', source)
    if not users or users[-1].strip() in ('root', '0', '0:0'):
        raise ValueError('Runtime overlay requires an explicit non-root image USER')
    requirements = '.abb-runtime/agentbench/runtime/docker/requirements.txt'
    if not (context / requirements).is_file():
        raise ValueError('Injected runtime requirements are missing')
    # Use the final stage's PATH, including an Agent-selected virtual environment.
    # pip evaluates Python markers here, never against the host's interpreter.
    dockerfile.write_text(source + '\nUSER root\n'
        f'COPY {requirements} /opt/abb-runtime-deps/requirements.txt\n'
        'RUN python -m pip --version >/dev/null 2>&1 || python -m ensurepip --default-pip\n'
        'RUN python -m pip --isolated install --no-cache-dir --index-url https://pypi.org/simple '
        '-r /opt/abb-runtime-deps/requirements.txt\nUSER ' + users[-1] + '\n')
