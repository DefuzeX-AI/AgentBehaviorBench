"""Acquire the unchanged native default embedding weights during image build."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    spec = json.loads((ROOT / "embedding-model.json").read_text())
    destination = ROOT / "models" / spec["filename"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".part")
    digest, size = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(spec["url"], timeout=120) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                digest.update(block)
                size += len(block)
                output.write(block)
        if size != spec["size_bytes"] or digest.hexdigest() != spec["sha256"]:
            raise ValueError("Native embedding model size/SHA256 does not match pinned provenance")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Verified native embedding model: {size} bytes, SHA256 {digest.hexdigest()}")


if __name__ == "__main__":
    main()
