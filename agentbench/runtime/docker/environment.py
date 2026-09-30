"""Describe the actual Docker arguments without exposing host paths or secrets."""
from agentbench.runtime.contracts.environment import ExecutionEnvironment


def describe_environment(arguments, *, workdir, egress, interception, timeout):
    values = {}
    mounts = []
    iterator = iter(arguments)
    for argument in iterator:
        if argument == '--mount':
            fields = dict(part.split('=', 1) if '=' in part else (part, True)
                          for part in next(iterator).split(','))
            # Never include source= host paths in the public environment.
            mounts.append({'path': fields['target'], 'kind': fields.get('type', 'bind'),
                           'read_only': bool(fields.get('readonly', False))})
        elif argument.startswith('--tmpfs='):
            path, options = argument.partition('=')[2].split(':', 1)
            parts = options.split(',')
            mounts.append({'path': path, 'kind': 'tmpfs', 'read_only': 'ro' in parts,
                           'executable': 'noexec' not in parts,
                           'size': next((part[5:] for part in parts if part.startswith('size=')), None)})
        elif argument.startswith(('--cpus=', '--memory=', '--pids-limit=')):
            key, value = argument[2:].split('=', 1)
            values[key] = value
    values['timeout_seconds'] = timeout
    network = {'mode': 'internal'}
    if interception is not None:
        network = {'mode': 'intercepted', 'other_egress': egress.mode,
                   'loopback': 'native_unobserved',
                   'external_ipv6': 'blocked', 'external_non_dns_udp': 'blocked',
                   'allow_rules': egress.rules() if egress.mode == 'observe' else []}
    return ExecutionEnvironment(
        runtime='docker', working_directory=workdir, limits=values,
        filesystem={'root_read_only': '--read-only' in arguments, 'mounts': mounts,
                    'capabilities_dropped': 'ALL' if '--cap-drop=ALL' in arguments else None,
                    'no_new_privileges': '--security-opt=no-new-privileges' in arguments},
        network=network)
