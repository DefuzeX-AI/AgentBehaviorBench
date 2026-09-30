"""Install fail-closed Linux network namespace rules."""
import subprocess

PROXY_PORT = 8080


def configure_netfilter() -> None:
    commands = [
        # Local services are Agent internals, not egress. Preserve native socket
        # semantics (including refused ports and server-first protocols) without
        # requiring per-service ports or HTTP tool routes. Match both interface
        # and destination so this exemption cannot admit non-loopback traffic.
        ["iptables", "-t", "nat", "-A", "OUTPUT", "-o", "lo", "-d", "127.0.0.0/8", "-j", "RETURN"],
        # Match the original Docker DNS destination because Docker may have
        # already DNAT'ed its port.
        ["iptables", "-t", "nat", "-A", "OUTPUT", "-p", "tcp", "-m", "conntrack", "--ctorigdst", "127.0.0.11", "--ctorigdstport", "53", "-j", "RETURN"],
        ["iptables", "-t", "nat", "-A", "OUTPUT", "-p", "tcp", "-m", "owner", "!", "--uid-owner", "0", "-j", "REDIRECT", "--to-ports", str(PROXY_PORT)],
        ["iptables", "-A", "OUTPUT", "-m", "owner", "--uid-owner", "0", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-o", "lo", "-d", "127.0.0.0/8", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-p", "udp", "-m", "conntrack", "--ctorigdst", "127.0.0.11", "--ctorigdstport", "53", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-p", "tcp", "-d", "127.0.0.11", "-m", "conntrack", "--ctorigdstport", "53", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-p", "tcp", "-d", "127.0.0.1", "--dport", str(PROXY_PORT), "-j", "ACCEPT"],
        # Preserve replies on admitted connections. New non-local outbound
        # connections still pass through the proxy or fail closed.
        ["iptables", "-A", "OUTPUT", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"],
        ["iptables", "-A", "OUTPUT", "-j", "REJECT"],
        # IPv6 loopback is native too. External IPv6 remains unsupported.
        ["ip6tables", "-A", "OUTPUT", "-o", "lo", "-d", "::1/128", "-j", "ACCEPT"],
        ["ip6tables", "-A", "OUTPUT", "-m", "owner", "!", "--uid-owner", "0", "-j", "REJECT"],
    ]
    for command in commands:
        subprocess.run(command, check=True)
