from __future__ import annotations

import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _host_target_triple() -> str:
    out = subprocess.check_output(["rustc", "-vV"], text=True)  # nosec B603 B607
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Failed to read rust host target triple.")


def main() -> None:
    root = _repo_root()
    target = _host_target_triple()
    is_windows = "windows" in target
    binaries_dir = root / "frontend" / "src-tauri" / "binaries"
    binaries_dir.mkdir(parents=True, exist_ok=True)

    sidecar_name = f"mcube-backend-{target}{'.exe' if is_windows else ''}"
    sidecar_path = binaries_dir / sidecar_name
    if sidecar_path.exists():
        print(f"Sidecar already exists: {sidecar_path}")
        return

    # Dev fallback: copy current python executable as a placeholder so tauri build checks pass.
    # In debug mode, Rust sidecar launch is skipped, so this placeholder is never executed.
    src = Path(sys.executable).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Python executable not found: {src}")

    shutil.copy2(src, sidecar_path)
    print(f"Created dev placeholder sidecar: {sidecar_path}")


if __name__ == "__main__":
    main()
