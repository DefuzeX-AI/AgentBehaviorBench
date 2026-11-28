"""Configure transparent routing and launch mitmdump."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import ServiceConfig, CONFIG_ENV, DEFAULT_CONFIG
from .proxy.netfilter import PROXY_PORT, configure_netfilter




def main() -> int:
    config_path = os.environ.get(CONFIG_ENV, DEFAULT_CONFIG)
    config = ServiceConfig.load(config_path)
    from .proxy.startup import preflight_targets
    from .observation import events
    try:
        preflight_targets(config)
    except Exception as exc:
        # Do not serialize arbitrary exception text containing transport credentials.
        events.emit('interceptor_startup_error', agent_id=config.agent_id,
                    error_code=getattr(exc, 'code', 'target_preflight_failed'))
        return 1
    Path("/run/defuzex/ca").mkdir(mode=0o700, parents=True, exist_ok=True)
    configure_netfilter()
    addon_path = Path(__file__).parent / "proxy" / "loader.py"
    command = [
        "mitmdump",
        "--quiet",
        "--mode",
        "transparent",
        "--listen-host",
        "0.0.0.0",
        "--listen-port",
        str(PROXY_PORT),
        "--showhost",
        "--set",
        "confdir=/run/defuzex/ca",
        "--set",
        "connection_strategy=lazy",
        "--set",
        "rawtcp=false",
        "--set",
        "upstream_cert=false",
        "--scripts",
        str(addon_path),
    ]
    # Do not use allow_hosts: excluded hosts bypass HTTP policy inspection.
    os.execvp(command[0], command)
    return 1


if __name__ == "__main__":
    sys.exit(main())
