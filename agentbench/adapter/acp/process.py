"""Own process groups so Agent-created children cannot outlive their attempt."""
import asyncio
import os
import signal

TRUST_KEYS = ('SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE', 'NODE_EXTRA_CA_CERTS',
              'GRPC_DEFAULT_SSL_ROOTS_FILE_PATH', 'GIT_SSL_CAINFO', 'CURL_CA_BUNDLE',
              'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')
BASE_KEYS = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT')


def child_environment(config, *, target=None):
    environment = {key: os.environ[key] for key in (*BASE_KEYS, *TRUST_KEYS, *config.env_keys)
            if key in os.environ}
    for key, value in (target or {}).items():
        if key in ('NODE_OPTIONS', 'JAVA_TOOL_OPTIONS') and environment.get(key):
            value = environment[key] + ' ' + value
        environment[key] = value
    return environment


async def terminate_group(process, timeout, *, flush_descendants=False):
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
    if flush_descendants and process.returncode is None and process.stdin:
        # EOF lets a stdio Agent run its normal SDK shutdown handlers.
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout)
        except asyncio.TimeoutError:
            pass
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    send(signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), timeout)
        if flush_descendants and os.name == 'posix':
            # A bridge can exit before its Gateway finishes exporting on SIGTERM.
            while (remaining := deadline - loop.time()) > 0:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                await asyncio.sleep(min(0.05, remaining))
    except asyncio.TimeoutError:
        pass
    finally:
        # Descendants may survive even after the leader has exited.
        send(signal.SIGKILL)
    await asyncio.wait_for(process.wait(), timeout)
