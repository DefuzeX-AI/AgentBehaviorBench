"""Launch script for open-code-review native ACP adapter."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
OCR_ACP_BIN = "/opt/agent/bin/ocr-acp"
OCR_BIN = "/opt/agent/bin/opencodereview"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    if not base_url:
        raise ValueError(f"{BASE_URL_ENV} is required")
    if not model:
        raise ValueError(f"{MODEL_ENV} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")

    if model.startswith("deepseek/"):
        model = model[len("deepseek/"):]

    child_env = {**environ, "HOME": str(home)}
    # Direct OCR CLI to use OpenAI-compatible endpoint
    child_env["OCR_LLM_URL"] = f"{base_url}/v1"
    child_env["OCR_LLM_TOKEN"] = key
    child_env["OCR_LLM_MODEL"] = model
    child_env["OCR_LLM_PROTOCOL"] = "openai"

    command = [
        OCR_ACP_BIN,
        "--ocr-binary", OCR_BIN,
        "--parser-provider", "openai",
        "--parser-model", model,
        "--parser-base-url", f"{base_url}/v1",
    ]
    child_env["OCR_ACP_PARSER_API_KEY"] = key

    # Write git configuration for the child home
    (home / ".gitconfig").write_text(
        "[safe]\n\tdirectory = *\n"
        "[user]\n\tname = Agent\n\temail = agent@abb.local\n",
        encoding="utf-8",
    )

    return command, child_env


def parse_unified_diff(text: str) -> dict[str, tuple[str, str]]:
    files = {}
    current_file = None
    old_lines: list[str] = []
    new_lines: list[str] = []
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("--- "):
            pass
        elif line.startswith("+++ "):
            if current_file and (old_lines or new_lines):
                files[current_file] = ("\n".join(old_lines), "\n".join(new_lines))
            path = line[4:].strip()
            if "\t" in path:
                path = path.split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            elif path.startswith("a/"):
                path = path[2:]
            current_file = path
            old_lines = []
            new_lines = []
            in_hunk = False
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk:
            if line.startswith("+"):
                new_lines.append(line[1:])
            elif line.startswith("-"):
                old_lines.append(line[1:])
            elif line.startswith(" "):
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line == "":
                old_lines.append("")
                new_lines.append("")
    if current_file and (old_lines or new_lines):
        files[current_file] = ("\n".join(old_lines), "\n".join(new_lines))
    return files


def run_git(args: list[str], cwd: Path, environ: dict[str, str]) -> None:
    subprocess.run(
        ["git"] + args,
        cwd=cwd,
        env=environ,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def apply_diff_to_repo(workspace: Path, text: str, environ: dict[str, str]) -> str:
    if not (workspace / ".git").is_dir():
        run_git(["init", "-b", "main"], cwd=workspace, environ=environ)
        run_git(["config", "user.name", "Agent"], cwd=workspace, environ=environ)
        run_git(["config", "user.email", "agent@abb.local"], cwd=workspace, environ=environ)
        (workspace / ".gitkeep").touch()
        run_git(["add", ".gitkeep"], cwd=workspace, environ=environ)
        run_git(["commit", "-m", "init"], cwd=workspace, environ=environ)
    files = parse_unified_diff(text)
    if files:
        for p, (old_c, new_c) in files.items():
            fp = workspace / p
            fp.parent.mkdir(parents=True, exist_ok=True)
            if old_c.strip():
                fp.write_text(old_c + "\n", encoding="utf-8")
            else:
                fp.touch()
            run_git(["add", p], cwd=workspace, environ=environ)
            run_git(["commit", "-m", f"initial {p}"], cwd=workspace, environ=environ)
            fp.write_text(new_c + "\n", encoding="utf-8")
        paths_str = ", ".join(files.keys())
        return f"Staged provided diff for {paths_str} in /home/agent/workspace; line numbers correspond directly to the prompt diff."
    import re
    match = re.search(r"```(?:python|py|go|js|ts|java|c|cpp)?\n(.*?)\n```", text, re.DOTALL)
    if match:
        code = match.group(1).strip()
        if code:
            m_file = re.search(r"(?:^|\n)\s*(?:#\s*)?(?:file|path)\s*:\s*(?:/home/agent/workspace/)?([^\n`]+?\.[a-zA-Z0-9]+)", text, re.I)
            raw_path = m_file.group(1).strip().strip("'\"").lstrip("/") if m_file else "app.py"
            fp = workspace / raw_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.touch()
            run_git(["add", str(raw_path)], cwd=workspace, environ=environ)
            run_git(["commit", "-m", f"initial {raw_path}"], cwd=workspace, environ=environ)
            fp.write_text(code + "\n", encoding="utf-8")
            line_count = len(code.splitlines())
            return f"Staged provided file {raw_path} ({line_count} lines) in /home/agent/workspace; line numbers 1-{line_count} correspond directly to the prompt code snippet."
    return ""


def open_directories(root: Path) -> None:
    uid = os.getuid()
    for current, dirs, files in os.walk(root):
        for name in dirs:
            path = Path(current, name)
            try:
                if not path.is_symlink() and path.stat().st_uid == uid:
                    path.chmod(0o777)
            except OSError:
                pass
        for name in files:
            path = Path(current, name)
            try:
                if not path.is_symlink() and path.stat().st_uid == uid:
                    path.chmod(0o666)
            except OSError:
                pass


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-ocr-home-"))
        command, environ = prepare(dict(os.environ), home)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1

    os.umask(0)
    workspace = Path.cwd()
    run_git(["config", "--global", "--add", "safe.directory", "*"], cwd=workspace, environ=environ)
    if not (workspace / ".git").is_dir():
        run_git(["init", "-b", "main"], cwd=workspace, environ=environ)
        run_git(["config", "user.name", "Agent"], cwd=workspace, environ=environ)
        run_git(["config", "user.email", "agent@abb.local"], cwd=workspace, environ=environ)
        (workspace / ".gitkeep").touch()
        run_git(["add", ".gitkeep"], cwd=workspace, environ=environ)
        run_git(["commit", "-m", "init"], cwd=workspace, environ=environ)

    child = subprocess.Popen(
        command,
        env=environ,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))

    staged_info = [""]

    def client_to_agent() -> None:
        try:
            for line in sys.stdin.buffer:
                try:
                    if b'"session/prompt"' in line:
                        msg = json.loads(line)
                        if msg.get("method") == "session/prompt":
                            modified = False
                            for item in msg.get("params", {}).get("prompt", []):
                                if isinstance(item, dict) and item.get("type") == "text":
                                    info = apply_diff_to_repo(workspace, item.get("text", ""), environ)
                                    if info:
                                        staged_info[0] = info
                                        item["text"] = "/review"
                                        modified = True
                            if modified:
                                line = json.dumps(msg).encode("utf-8") + b"\n"
                except Exception:
                    pass
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    threading.Thread(target=client_to_agent, daemon=True).start()
    out = sys.stdout.buffer
    prefixed = False
    try:
        for line in child.stdout:
            try:
                if not prefixed and b'"agent_message_chunk"' in line:
                    msg = json.loads(line)
                    content = msg.get("params", {}).get("update", {}).get("content", {})
                    if isinstance(content, dict) and content.get("type") == "text":
                        prefix = staged_info[0] + "\n\n" if staged_info[0] else ""
                        content["text"] = prefix + content.get("text", "")
                        line = json.dumps(msg).encode("utf-8") + b"\n"
                        prefixed = True
            except Exception:
                pass
            out.write(line)
            out.flush()
    except (BrokenPipeError, OSError):
        pass
    finally:
        open_directories(workspace)
        channel = Path("/run/abb-channel")
        if channel.is_dir():
            open_directories(channel)

    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
