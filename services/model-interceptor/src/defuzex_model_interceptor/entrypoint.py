"""Configure transparent routing and launch mitmdump."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import ServiceConfig


CONFIG_ENV = "DEFUZEX_INTERCEPTOR_CONFIG"
DEFAULT_CONFIG = "/run/secrets/interceptor_config"
PROXY_PORT = 8080


def main() -> int:
    config_path = os.environ.get(CONFIG_ENV, DEFAULT_CONFIG)
    ServiceConfig.load(config_path)  # Validate before modifying the namespace.
    Path("/run/defuzex/ca").mkdir(mode=0o700, parents=True, exist_ok=True)
    _configure_netfilter()
    addon_path = Path(__file__).with_name("loader.py")
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


def _configure_netfilter() -> None:
    commands = [
        # Docker DNS is the only direct non-proxy service. Match the original
        # destination because Docker may have already DNAT'ed its port.
        ["iptables", "-t", "nat", "-A", "OUTPUT", "-p", "tcp", "-m", "conntrack", "--ctorigdst", "127.0.0.11", "--ctorigdstport", "53", "-j", "RETURN"],
        ["iptables", "-t", "nat", "-A", "OUTPUT", "-p", "tcp", "-m", "owner", "!", "--uid-owner", "0", "-j", "REDIRECT", "--to-ports", str(PROXY_PORT)],
        ["iptables", "-A", "OUTPUT", "-m", "owner", "--uid-owner", "0", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-p", "udp", "-m", "conntrack", "--ctorigdst", "127.0.0.11", "--ctorigdstport", "53", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-p", "tcp", "-d", "127.0.0.11", "-m", "conntrack", "--ctorigdstport", "53", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-p", "tcp", "-d", "127.0.0.1", "--dport", str(PROXY_PORT), "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-j", "REJECT"],
        # IPv6 and QUIC are not translated by this release: fail closed.
        ["ip6tables", "-A", "OUTPUT", "-m", "owner", "!", "--uid-owner", "0", "-j", "REJECT"],
    ]
    for command in commands:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    sys.exit(main())
