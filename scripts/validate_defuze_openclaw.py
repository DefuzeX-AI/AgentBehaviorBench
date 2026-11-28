"""Run one real OpenClaw turn through Defuze and retain sanitized acceptance evidence."""
import json
import argparse
import subprocess
import os
from pathlib import Path
import sys
from functools import partial
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentbench.cli.environment import load_project_environment
from agentbench.observe.catalog import enabled_agents, select_agent, resolve_agent
from agentbench.observe.chat import ChatSession, _text
from agentbench.observe.store import atomic_json, environment_secrets
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.docker.policy import DockerPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', default='openclaw')
    parser.add_argument('--memory', help='Override only the Agent container memory for a controlled comparison')
    args = parser.parse_args()
    load_project_environment(ROOT / '.env')
    env = dict(os.environ)
    # This explicit acceptance check must use the requested dotenv credential,
    # even when the desktop process inherited an older KUMA key.
    env.update({key: value for key, value in dotenv_values(ROOT / '.env').items() if value is not None})
    # Exercise the application's selected default, without printing any env values.
    from agentbench.runtime.interception.providers import resolve_model_provider
    target = resolve_model_provider(environ=env).resolve(env)
    if target.provider_id != 'defuze_server':
        raise RuntimeError('Select defuze_server before running this acceptance check')
    registry = ROOT / 'resources/registry.toml'
    agent = resolve_agent(select_agent(enabled_agents(registry), args.agent), registry)
    marker = 'DEFUZE_' + agent.agent_id.upper().replace('-', '_') + '_OK 323'
    runtime = partial(DockerRuntime, policy=DockerPolicy(memory=args.memory)) if args.memory else DockerRuntime
    chat = ChatSession(agent, output=ROOT.parent/('outputs/defuze-' + agent.agent_id), environ=env,
                       runtime_factory=runtime)
    status, failure, result = 'succeeded', None, {}
    try:
        print('Starting ' + agent.agent_id + ' with Defuze Server', flush=True)
        print('Run directory:', chat.start(), flush=True)
        result = chat.send('Use your terminal tool to calculate 17 * 19 and write the result to '
                           'defuze-smoke.txt in the current workspace. Read it back using a tool. '
                           'Then reply with exactly: ' + marker)
        if result.get('status') != 'succeeded' or marker not in _text(result.get('output')):
            status, failure = 'failed', 'Agent turn did not return the requested acceptance marker'
    except Exception as exc:
        status, failure = 'failed', f'{type(exc).__name__}: {exc}'
        for secret in environment_secrets(env):
            failure = failure.replace(secret, '[REDACTED]')
    if chat.directory is not None:
        capture_resources(chat, env)
    run = chat.close(status, failure)
    if chat.directory is None:
        print(failure, flush=True)
        return 1
    events = []
    network = chat.directory/'logs/network.jsonl'
    if network.exists():
        for line in network.read_text(encoding='utf-8').splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    summary = {'run': run, 'turn_status': result.get('status'),
               'response': _text(result.get('output')), 'network_event_count': len(events),
               'provider': target.provider_id, 'target_url': target.base_url, 'model': target.model}
    atomic_json(chat.directory/'acceptance.json', summary)
    print(json.dumps({'status': (run or {}).get('status'), 'turn_status': result.get('status'),
                      'directory': str(chat.directory), 'error': failure}, ensure_ascii=True), flush=True)
    return 0 if run and run['status'] == 'succeeded' and status == 'succeeded' else 1


def capture_resources(chat, env):
    """Retain cgroup counters and process state before the owned container is removed."""
    def command(args):
        return subprocess.run(['docker', *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=15)
    try:
        names = command(['ps', '-a', '--filter', 'label=abb.artifact_run_id=' + chat.directory.name,
                         '--filter', 'label=abb.role=agent', '--format', '{{.Names}}']).stdout.splitlines()
        if len(names) != 1:
            return
        state = command(['inspect', '--format', '{{json .State}}', names[0]])
        counters = command(['exec', names[0], 'python', '-c',
            "import json; from pathlib import Path; names=('memory.max','memory.current','memory.peak','memory.events','pids.current','pids.max'); "
            "print(json.dumps({n:(Path('/sys/fs/cgroup')/n).read_text() for n in names if (Path('/sys/fs/cgroup')/n).exists()}))"])
        logs = command(['exec', names[0], 'python', '-c',
            "import json; from pathlib import Path; print(json.dumps({str(p):p.read_text(errors='replace')[-16000:] for p in Path('/tmp').glob('abb-openclaw-home-*/gateway.log')}))"])
        data = json.dumps({'state': state.stdout, 'cgroup': counters.stdout, 'gateway_logs': logs.stdout})
        for secret in environment_secrets(env):
            data = data.replace(secret, '[REDACTED]')
        (chat.directory/'gateway-diagnostics.json').write_text(data, encoding='utf-8')
    except (OSError, subprocess.TimeoutExpired) as exc:
        atomic_json(chat.directory/'gateway-diagnostics.json', {'capture_error': type(exc).__name__})


if __name__ == '__main__':
    raise SystemExit(main())
