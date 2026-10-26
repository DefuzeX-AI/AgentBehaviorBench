"""Install an unmodified, checksum-pinned official MicroClaw release."""
from pathlib import Path
import hashlib
import io
import json
import platform
import sys
import tarfile
import urllib.request
VERSION = "0.10.1"
def install(destination):
    descriptor = json.loads(Path("/opt/agent/agent/abb-native-release.json").read_text())
    if descriptor["version"] != VERSION:
        raise ValueError("Unexpected release descriptor version")
    artifact = descriptor["artifacts"][platform.machine()]
    arch = artifact["name"]
    expected = artifact["sha256"]
    url = artifact["url"]
    prefix = f"https://github.com/microclaw/microclaw/releases/download/v{VERSION}/"
    if not url.startswith(prefix) or not artifact["name"].startswith(f"microclaw-{VERSION}-"):
        raise ValueError("Unexpected official artifact URL")
    request = urllib.request.Request(url, headers={"User-Agent": "AgentBehaviorBench/0.1"})
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = response.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Official MicroClaw archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        member = archive.getmember("microclaw")
        if not member.isfile():
            raise ValueError("Expected a regular native binary")
        binary = archive.extractfile(member).read()
    target = Path(destination)
    target.write_bytes(binary)
    target.chmod(0o755)
    print("Installed official MicroClaw", VERSION, arch, "archive SHA256", expected)
if __name__ == "__main__":
    install(sys.argv[1])
