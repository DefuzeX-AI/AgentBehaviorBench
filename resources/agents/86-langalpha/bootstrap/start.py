"""Start an actual local SSH service, then hand control to the ABB worker."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

state = Path.home() / "abb-ssh"
state.mkdir(mode=0o700, exist_ok=True)
for name in ("host", "client"):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(state/name)], check=True)
(state/"authorized_keys").write_text((state/"client.pub").read_text())
(state/"authorized_keys").chmod(0o600)
(state/"sshd_config").write_text("\n".join([
    "ListenAddress 127.0.0.1", "Port 2222", f"HostKey {state/'host'}",
    f"PidFile {state/'sshd.pid'}", f"AuthorizedKeysFile {state/'authorized_keys'}",
    "PasswordAuthentication no", "KbdInteractiveAuthentication no", "UsePAM no",
    "PermitRootLogin no", "AllowUsers agent", "StrictModes yes",
    "Subsystem sftp internal-sftp", "LogLevel ERROR", "",
]))
log = (state/"sshd.log").open("w")
service = subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(state/"sshd_config")], stdout=log, stderr=log)
for _ in range(40):
    if service.poll() is not None:
        raise RuntimeError("Local SSH service failed: " + (state/"sshd.log").read_text())
    try:
        with socket.create_connection(("127.0.0.1", 2222), timeout=1):
            break
    except OSError:
        time.sleep(0.25)
else:
    raise RuntimeError("Local SSH service did not become ready")
os.chdir("/opt/agent/agent")
