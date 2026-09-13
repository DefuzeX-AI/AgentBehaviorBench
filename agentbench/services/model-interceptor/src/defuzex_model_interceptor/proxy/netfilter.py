"""Install fail-closed Linux network namespace rules."""
import subprocess

PROXY_PORT = 8080


def configure_netfilter() -> None:
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
