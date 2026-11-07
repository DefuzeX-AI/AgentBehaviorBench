"""Install an unmodified, checksum-pinned official OpenBitFun CLI release."""
from pathlib import Path
import hashlib
import io
import json
import os
import platform
import sys
import tarfile
import urllib.request

VERSION = "1.0.7"


def _read_archive(artifact: dict) -> bytes:
    """Prefer a pre-placed install/ copy (host download), else fetch the official URL."""
    local = Path("/opt/agent/agent") / artifact["name"]
    if local.is_file():
        raw = local.read_bytes()
        source = f"local:{local.name}"
    else:
        # Ignore broken build-time proxies (e.g. Docker Desktop -> :3128 refused).
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(key, None)
        request = urllib.request.Request(
            artifact["url"], headers={"User-Agent": "AgentBehaviorBench/0.1"}
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read(128 * 1024 * 1024 + 1)
        source = artifact["url"]
    if len(raw) > 128 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("Official OpenBitFun archive checksum mismatch")
    print("Loaded OpenBitFun archive from", source)
    return raw


def install(destination: str) -> None:
    descriptor = json.loads(Path("/opt/agent/agent/abb-native-release.json").read_text(encoding="utf-8"))
    if descriptor["version"] != VERSION:
        raise ValueError("Unexpected release descriptor version")
    artifact = descriptor["artifacts"][platform.machine()]
    expected = artifact["sha256"]
    url = artifact["url"]
    member_name = artifact["member"]
    prefix = f"https://github.com/GCWing/OpenBitFun/releases/download/v{VERSION}/"
    if not url.startswith(prefix) or not artifact["name"].startswith(f"openbitfun-cli-{VERSION}-"):
        raise ValueError("Unexpected official artifact URL")
    raw = _read_archive(artifact)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        member = archive.getmember(member_name)
        if not member.isfile():
            raise ValueError("Expected a regular native binary")
        binary = archive.extractfile(member).read()
    target = Path(destination)
    target.write_bytes(binary)
    target.chmod(0o755)
    print("Installed official OpenBitFun", VERSION, artifact["name"], "archive SHA256", expected)


if __name__ == "__main__":
    install(sys.argv[1])
