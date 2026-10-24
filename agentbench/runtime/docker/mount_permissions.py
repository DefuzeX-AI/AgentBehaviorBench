"""Assign exact private mount roots to the image user without world permissions."""
import os
from uuid import uuid4

# Runs in a temporary, networkless container. Only declared job-owned
# directory roots are mounted; no host parent, Docker socket or credentials.
_SCRIPT = """
import grp, os, pwd, sys
user, _, group = sys.argv[1].partition(':')
if user.isdecimal():
    uid = int(user)
    try:
        default_gid = pwd.getpwuid(uid).pw_gid
    except KeyError:
        default_gid = 0
else:
    entry = pwd.getpwnam(user)
    uid, default_gid = entry.pw_uid, entry.pw_gid
gid = (int(group) if group.isdecimal() else grp.getgrnam(group).gr_gid) if group else default_gid
if uid == 0:
    raise ValueError('Private mounts require a non-root owner')
def assign(path):
    import stat
    try:
        info = os.lstat(path)
    except OSError:
        # Windows system files such as desktop.ini surface in os.listdir
        # through the bind mount but cannot be stat'ed from the container;
        # skip them rather than failing the whole mount preparation.
        return
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('Private mounts cannot contain links')
    if stat.S_ISDIR(info.st_mode):
        os.chown(path, 0, 0)
        os.chmod(path, 0o700)
        for name in os.listdir(path):
            assign(os.path.join(path, name))
        os.chown(path, uid, gid)
    elif stat.S_ISREG(info.st_mode):
        os.chown(path, uid, gid)
    else:
        raise ValueError('Private mounts cannot contain special files')
private_count = int(sys.argv[2])
host_uid = int(sys.argv[3])
for index, path in enumerate(sys.argv[4:]):
    if index < private_count:
        assign(path)
    else:
        # The host must retain ownership to create future Attempt directories.
        # Only this root gets group write access; never re-own old Case files.
        os.chown(path, host_uid, gid)
        os.chmod(path, 0o770)
"""


def prepare_mounts(runtime, image, directories, deadline, *, shared=()):
    if not directories and not shared:
        return
    user = runtime._run('image', 'inspect', '--format', '{{.Config.User}}', image,
                        deadline=deadline).stdout.strip()
    name = 'defuzex-' + uuid4().hex + '-mounts'
    roots = []
    for directory in (*dict.fromkeys(directories), *dict.fromkeys(shared)):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Private mount root must be a real directory')
        roots.append(directory.resolve())
    command = ['create', '--name', name, *runtime._labels('mount-permissions', name),
               '--network', 'none', '--user', '0',
               '--cap-drop=ALL', '--cap-add=CHOWN', '--cap-add=FOWNER',
               '--security-opt=no-new-privileges', '--entrypoint', 'python']
    targets = []
    for index, root in enumerate(roots):
        target = f'/private-mount-{index}'
        command += ['--mount', f'type=bind,source={root},target={target}']
        targets.append(target)
    command += [image, '-I', '-S', '-c', _SCRIPT, user, str(len(dict.fromkeys(directories))),
                str(getattr(os, 'getuid', lambda: 0)()), *targets]
    runtime._plan_resource('container', name, 'mount-permissions', name)
    try:
        runtime._create_resource('container', name, command, deadline=deadline)
        runtime._run('start', '--attach', name, deadline=deadline)
        result = runtime._run('inspect', '--format', '{{.State.ExitCode}}', name, deadline=deadline)
        if result.stdout.strip() != '0':
            raise RuntimeError('Cannot assign private mount ownership to image user')
    finally:
        from agentbench.runtime.contracts.execution import Deadline
        runtime._remove_resource('container', name,
                                 deadline=Deadline.after(runtime._limits.cleanup_seconds))
