"""Own process groups so Agent-created children cannot outlive their attempt."""
import asyncio
import os
import signal

TRUST_KEYS = ('SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE', 'NODE_EXTRA_CA_CERTS',
              'GRPC_DEFAULT_SSL_ROOTS_FILE_PATH', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')
BASE_KEYS = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT')


def child_environment(config):
    return {key: os.environ[key] for key in (*BASE_KEYS, *TRUST_KEYS, *config.env_keys)
            if key in os.environ}


async def terminate_group(process, timeout):
    if process is None:
        return
    def send(sig):
        try:
            if os.name == 'posix':
                os.killpg(process.pid, sig)
            elif process.returncode is None:
                process.terminate() if sig == signal.SIGTERM else process.kill()
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        # Descendants may survive even after the leader has exited.
        send(signal.SIGKILL)
    await asyncio.wait_for(process.wait(), timeout)
