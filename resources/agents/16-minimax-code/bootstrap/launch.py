"""Configure native BYOK in an isolated profile, then hand stdio over to ACP."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


KEY_ENV = 'MINIMAX_API_KEY'


def prepare(unit, environ):
    """Return (native CLI argv, child environment) after saving the API key.

    Args:
        unit: Outer Agent unit directory containing agent/ and bootstrap/.
        environ: Runtime variables, including MINIMAX_API_KEY and MINIMAX_DATA_DIR.
    Returns:
        A command prefix and environment for the native ACP process.
    Raises:
        ValueError for a missing key; RuntimeError for native setup failure.
    No upstream source is edited. Secrets stay in the disposable profile and
    environment, never command arguments or the template copied into the image.
    """
    key = environ.get(KEY_ENV, '').strip()
    if not key:
        raise ValueError(f'{KEY_ENV} is required for MiniMax API-key mode')
    base = Path(environ['MINIMAX_DATA_DIR'])
    base.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix='abb-byok-', dir=base))
    env = {**environ, 'MAVIS_TUI_LLM_CONTEXT_INSPECTOR': '1', KEY_ENV: key, 'MINIMAX_DATA_DIR': str(profile), 'MAVIS_DATA_DIR': str(profile)}
    cli = ['node', str(unit / 'agent/dist/cli.js')]
    try:
        config = profile / 'config.yaml'
        with open(config, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            stream.write((unit / 'bootstrap/native-config.yaml').read_text())
        result = subprocess.run([*cli, 'provider', 'set-minimax-key', '--api-key-env', KEY_ENV],
                                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=45)
        if result.returncode:
            detail = (result.stdout or '').replace(key, '[REDACTED]')[-2000:]
            raise RuntimeError(f'MiniMax native BYOK setup failed ({result.returncode}): {detail}')
    except subprocess.TimeoutExpired:
        shutil.rmtree(profile)
        raise RuntimeError('MiniMax native BYOK setup timed out') from None
    except BaseException:
        shutil.rmtree(profile)
        raise
    return cli, env


def main():
    """Replace the launcher with ACP, keeping stdout exclusively for JSON-RPC."""
    try:
        cli, env = prepare(Path(__file__).resolve().parents[1], dict(os.environ))
        os.execvpe(cli[0], [*cli, 'acp'], env)
    except (OSError, ValueError, RuntimeError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or '\0', '[REDACTED]')
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
