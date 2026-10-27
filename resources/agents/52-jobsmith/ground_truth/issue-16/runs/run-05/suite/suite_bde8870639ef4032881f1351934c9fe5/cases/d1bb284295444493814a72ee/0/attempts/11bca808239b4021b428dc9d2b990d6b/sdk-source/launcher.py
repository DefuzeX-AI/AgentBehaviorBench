"""打包用啟動器（PyInstaller 進入點）：啟動內建伺服器並開預設瀏覽器。

雙擊 Jobsmith.exe → 啟動本機伺服器 → 自動開瀏覽器到 App；關閉這個視窗即停止伺服器。
仍是在你本機執行、用你自己的 Claude Code / Codex CLI 訂閱或自備 Key（與 run.bat 同一後端）。

可寫入檔案（SQLite、.env）放在 exe 旁邊：
- exe 旁的 .env：存你的 BYOK 金鑰等（OPENAI_* 等）。
- exe 旁的 JobsmithData/：投遞包歷史、記憶、LangGraph checkpoints。
唯讀資源（前端 dist、demo 資料）打包在 exe 內。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _setup_frozen() -> None:
    """凍結成 exe 時，把可寫入檔案導向 exe 旁的位置（打包內部是唯讀的），並載入 exe 旁的 .env。"""
    if not getattr(sys, "frozen", False):
        return
    exe_dir = Path(sys.executable).parent
    data_dir = exe_dir / "JobsmithData"
    try:
        data_dir.mkdir(exist_ok=True)
    except Exception:
        data_dir = exe_dir
    os.environ.setdefault("COPILOT_DB", str(data_dir / "checkpoints.sqlite"))
    os.environ.setdefault("COPILOT_APP_DB", str(data_dir / "app.sqlite"))
    env_file = exe_dir / ".env"
    os.environ.setdefault("COPILOT_ENV_FILE", str(env_file))
    try:
        from dotenv import load_dotenv
        if env_file.exists():
            load_dotenv(env_file)
    except Exception:
        pass


_setup_frozen()

import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import webbrowser  # noqa: E402
from urllib.request import urlopen  # noqa: E402

import uvicorn  # noqa: E402


def _pick_port(preferred: int = 8000) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
        s2.bind(("127.0.0.1", 0))
        return s2.getsockname()[1]


def _wait_until_up(url: str, server: uvicorn.Server, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if getattr(server, "started", False):
            try:
                with urlopen(url, timeout=1):
                    return True
            except Exception:
                pass
        time.sleep(0.2)
    return False


def main() -> int:
    port = _pick_port(8000)
    base = f"http://127.0.0.1:{port}"

    config = uvicorn.Config("app.server:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    print("Jobsmith 啟動中，第一次可能要等幾秒…")
    if not _wait_until_up(base, server):
        print("伺服器啟動失敗。請確認 Windows 防火牆未封鎖本機連線。")
        try:
            input("按 Enter 結束…")
        except Exception:
            pass
        return 1

    print(f"已啟動：{base}")
    print("已為你開啟瀏覽器。關閉這個視窗即停止 Jobsmith。")
    try:
        webbrowser.open(base)
    except Exception:
        pass

    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
