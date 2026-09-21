"""Fetch exactly one commit and export a portable source archive."""
import os
import subprocess
import signal
import tempfile
import time


def run_git(directory, args, check):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            ['git', '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never',
             '-C', str(directory), *args], env=env, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.DEVNULL, start_new_session=os.name != 'nt')
        try:
            while process.poll() is None:
                check()
                time.sleep(0.05)
            check()
            if process.returncode:
                raise RuntimeError('Git source acquisition failed during ' + args[0])
            output.seek(0)
            return output.read().decode('utf-8')
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=10, check=False)
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                process.wait()


def export_source(spec, archive, check):
    with tempfile.TemporaryDirectory(prefix='abb-source-git-') as directory:
        run_git(directory, ['init', '--bare', '--quiet'], check)
        run_git(directory, ['fetch', '--quiet', '--depth=1', '--no-tags',
                            '--', spec.repository, spec.revision], check)
        actual = run_git(directory, ['rev-parse', 'FETCH_HEAD^{commit}'], check).strip()
        if actual != spec.revision:
            raise ValueError('Downloaded source commit does not match source.revision')
        tree = run_git(directory, ['ls-tree', '-r', actual], check)
        if any(line.startswith('160000 ') for line in tree.splitlines()):
            raise ValueError('Git source contains submodules; use bundled source until submodules are supported')
        run_git(directory, ['archive', '--format=zip', '--output=' + str(archive), actual], check)
