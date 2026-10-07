"""Shared logging and runtime helpers for executable examples.

Console output can be mirrored to per-run log files, while command and vision
events use a consistent compact format across cases.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def safe_component(value: str | None, default: str = "task") -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    return (safe.strip("._") or default)[:120]


# --------------------------------------------------------------------------- #




# --------------------------------------------------------------------------- #
import os as _os


VLM_PLATFORM_BASE_URL = _os.environ.get("VLM_PLATFORM_BASE_URL", "http://127.0.0.1:9000/v1")


def add_backbone_args(parser: Any) -> Any:
    """\u7ed9\u5355\u4f53 run_case \u52a0\u4e0e\u591a\u4f53\u4e00\u81f4\u7684\u8bc6\u56fe backbone \u65d7\u6807 (\u591a\u4f53\u5df2\u5728 add_common_args \u91cc\u6709, \u52ff\u91cd\u590d\u52a0)\u3002"""

    g = parser.add_argument_group("\u8bc6\u56fe backbone (\u547d\u4ee4\u884c\u5207\u6a21\u578b, \u7ecf /sim/vision/override \u8986\u76d6\u540e\u7aef\u8bc6\u56fe)")
    g.add_argument("--provider", default="qwen",
                   choices=["qwen", "self_host", "gpt", "gemini", "anthropic"],
                   help="\u8bc6\u56fe backbone \u4f9b\u5e94\u5546 (\u4ec5\u7528\u4e8e\u63a8\u65ad api-style; \u9ed8\u8ba4 qwen=OpenAI \u517c\u5bb9)")
    g.add_argument("--model", default=None, help="\u8bc6\u56fe\u6a21\u578b id (\u5982 qwen3vl-8b); \u4e0d\u4f20\u5219\u4f7f\u7528\u540e\u7aef .env \u914d\u7f6e")
    g.add_argument("--llm-base-url", default=None, help="OpenAI \u517c\u5bb9\u7aef\u70b9 (\u6307\u5411 VLM \u5e73\u53f0, \u5982 http://host:80/v1)")
    g.add_argument("--llm-api-key", default=None, help="\u8bc6\u56fe\u7aef\u70b9 api key (\u7f3a\u7701\u56de\u843d\u540e\u7aef .env)")
    g.add_argument("--llm-api-style", default=None, choices=["openai", "anthropic"],
                   help="\u63a5\u53e3\u98ce\u683c; \u7f3a\u7701: provider=anthropic\u2192anthropic, \u5176\u4f59\u2192openai")
    g.add_argument("--vlm-platform", action="store_true",
                   help=f"\u4f7f\u7528\u81ea\u6258\u7ba1 VLM (\u81ea\u52a8\u586b base-url={VLM_PLATFORM_BASE_URL} + openai \u98ce\u683c); "
                        f"\u8fd8\u9700\u8bbe\u7f6e --model\u3002\u4e0d\u52a0\u5219\u4f7f\u7528\u540e\u7aef .env \u914d\u7f6e\u3002")
    return parser


def push_vision_override(client: Any, args: Any, *, task_id: str = "") -> bool:
    """\u628a\u547d\u4ee4\u884c\u9009\u7684\u8bc6\u56fe backbone \u63a8\u7ed9\u540e\u7aef (\u9ed8\u8ba4\u4f5c\u5168\u5c40\u9ed8\u8ba4: taskId="")\u3002**\u81ea\u6e05\u7406**:

    - \u6307\u5b9a\u4e86 ``--model``/``--llm-base-url`` (\u6216 ``--vlm-platform``) \u2192 \u767b\u8bb0\u8986\u76d6 (\u8fd4\u56de True);
    - \u672a\u6307\u5b9a \u2192 \u4e3b\u52a8**\u6e05\u9664**\u8be5 taskId \u7684\u65e7\u8986\u76d6 (\u8fd4\u56de False), \u907f\u514d\u4e0a\u4e00\u6b21\u8fd0\u884c\u7684\u8986\u76d6\u6b8b\u7559\u6c61\u67d3\u672c\u6b21\u3002
    \u5728\u6bcf\u6b21 run \u542f\u52a8\u3001\u8fdb\u5165 episode \u5faa\u73af\u524d\u8c03\u7528\u4e00\u6b21\u5373\u53ef (\u5168\u5c40\u9ed8\u8ba4\u5bf9\u6240\u6709\u8f6e\u6b21 task_id \u751f\u6548)\u3002
    ``client`` \u9700\u6709 ``post_json(path, payload, timeout=...)``; \u5f02\u5e38\u53ea\u544a\u8b66\u4e0d\u629b\u3002
    """
    model = getattr(args, "model", None)
    base_url = getattr(args, "llm_base_url", None)
    
    if getattr(args, "vlm_platform", False) and not base_url:
        base_url = VLM_PLATFORM_BASE_URL
        if getattr(args, "llm_api_style", None) is None:
            try:
                args.llm_api_style = "openai"
            except Exception:  # noqa: BLE001
                pass
    
    prompt_text = None
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        try:
            prompt_text = Path(prompt_file).read_text(encoding="utf-8")
            print(f"[\u8bc6\u56fe] prompt \u8986\u76d6\u5df2\u8f7d\u5165: {prompt_file} ({len(prompt_text)} \u5b57\u7b26)", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[\u8bc6\u56fe] \u8bfb\u53d6 --prompt-file \u5931\u8d25(\u5ffd\u7565, \u7528\u5185\u7f6e prompt): {exc}", flush=True)
    if not (model or base_url or prompt_text):
        try:
            client.post_json("/sim/vision/override", {"taskId": task_id, "clear": True}, timeout=10.0)
        except Exception:  # noqa: BLE001
            pass
        return False
    
    
    style = getattr(args, "llm_api_style", None) or ("openai" if base_url else None)
    body = {"taskId": task_id, "model": model, "baseUrl": base_url,
            "apiKey": getattr(args, "llm_api_key", None), "apiStyle": style}
    if prompt_text:
        body["prompt"] = prompt_text
    try:
        client.post_json("/sim/vision/override", body, timeout=10.0)
        print(f"[\u8bc6\u56fe] backbone \u8986\u76d6\u5df2\u4e0b\u53d1: model={model or '(.env)'} "
              f"base={base_url or '(.env)'} style={style} prompt={'custom' if prompt_text else 'built-in'} "
              f"(taskId={task_id or '<global>'})", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[\u8bc6\u56fe] \u4e0b\u53d1 backbone \u8986\u76d6\u5931\u8d25(\u5ffd\u7565, \u56de\u843d .env): {exc}", flush=True)
        return False


class _Tee:
    """\u628a\u5199\u5165\u540c\u65f6\u5206\u53d1\u5230\u63a7\u5236\u53f0\u548c\u6587\u4ef6 \u2014\u2014 \u8ba9\u6240\u6709 print \u65e5\u5fd7\u5728\u63a7\u5236\u53f0\u53ef\u89c1\u7684\u540c\u65f6\u843d\u76d8\u3002"""

    def __init__(self, console: Any, fh: Any) -> None:
        self._console = console
        self._fh = fh

    def write(self, data: str) -> int:
        for s in (self._console, self._fh):
            try:
                s.write(data); s.flush()
            except Exception:  # noqa: BLE001
                pass
        return len(data)

    def flush(self) -> None:
        for s in (self._console, self._fh):
            try:
                s.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self) -> bool:
        try:
            return bool(self._console.isatty())
        except Exception:  # noqa: BLE001
            return False


def setup_console_logging(results_dir: Path | str, task_prefix: str) -> Path:
    """\u628a\u672c\u8fdb\u7a0b stdout/stderr \u540c\u65f6\u955c\u50cf\u5230 ``results/console_logs/<prefix>_<ts>.log``, \u8fd4\u56de\u6587\u4ef6\u8def\u5f84\u3002

    \u4e4b\u540e\u6240\u6709 print(\u884c\u52a8\u6307\u4ee4/HTTP/\u5f15\u64ce\u4ea4\u4e92/\u5927\u6a21\u578b\u4ea4\u4e92) \u90fd\u65e2\u6253\u63a7\u5236\u53f0\u3001\u53c8\u5b58\u6587\u4ef6\u3002\u91cd\u590d\u8c03\u7528\u5b89\u5168 (\u5e42\u7b49\u518d\u955c\u50cf)\u3002
    """

    results_dir = Path(results_dir)
    log_dir = results_dir / "console_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{safe_component(task_prefix)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    fh = path.open("a", encoding="utf-8", buffering=1)
    fh.write(f"# console log: {task_prefix} @ {datetime.now().isoformat(timespec='seconds')}\n")
    sys.stdout = _Tee(sys.__stdout__, fh)
    sys.stderr = _Tee(sys.__stderr__, fh)
    return path


def brief_cmd(cmd: object) -> str:
    """\u628a\u6307\u4ee4\u7684 command \u5b57\u6bb5\u7b80\u5199\u6210\u4e00\u884c (x/y/z \u6216 mile/raw/speed \u6216\u5176\u5b83\u5e38\u89c1\u952e)\u3002"""
    if not isinstance(cmd, dict):
        return str(cmd) if cmd else ""
    if any(k in cmd for k in ("x", "X")):
        return f"x={cmd.get('x', cmd.get('X'))},y={cmd.get('y', cmd.get('Y'))},z={cmd.get('z', cmd.get('Z'))}"
    keys = ("mile", "raw", "speed", "instructionType", "isMove", "amount", "pointNum", "location")
    parts = [f"{k}={cmd[k]}" for k in keys if k in cmd]
    return " ".join(parts) if parts else ", ".join(f"{k}={v}" for k, v in list(cmd.items())[:4])


def log_cmd(equip: str, label: str) -> None:
    """\u7edf\u4e00\u6253\u5370"\u5bf9\u88c5\u5907\u4e0b\u53d1\u7684\u6307\u4ee4"\u884c (\u7a81\u51fa\u663e\u793a, \u5e26\u56fe\u6807)\u3002"""
    print(f"\U0001f4e1 [\u6307\u4ee4] {equip} \u2190 {label}", flush=True)


# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #
def short_json(obj: Any, limit: int = 700) -> str:
    """\u628a\u5bf9\u8c61\u538b\u6210\u4e00\u884c JSON \u5e76\u622a\u65ad (\u4f9b\u8bf7\u6c42/\u56de\u6267\u65e5\u5fd7; \u8fc7\u957f\u52a0 ...(+N\u5b57\u7b26))\u3002"""
    import json as _json
    try:
        s = _json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s) - limit}\u5b57\u7b26)"


def log_http_req(method: str, path: str, payload: Any = None) -> None:
    """\u6253\u5370\u4e00\u6761\u540e\u7aef HTTP \u8bf7\u6c42 (POST \u5e26\u8f7d\u8377)\u3002"""
    if payload is None:
        print(f"[\u540e\u7aefHTTP] \u2192 \u53d1\u8bf7\u6c42({method}) {path}", flush=True)
    else:
        print(f"[\u540e\u7aefHTTP] \u2192 \u53d1\u8bf7\u6c42({method}) {path} \u8f7d\u8377={short_json(payload)}", flush=True)


def log_http_resp(method: str, path: str, data: Any) -> None:
    """\u6253\u5370\u4e00\u6761\u540e\u7aef HTTP \u6210\u529f\u56de\u6267\u3002"""
    print(f"[\u540e\u7aefHTTP] \u2190 \u6536\u54cd\u5e94({method}) {path} \u6210\u529f {short_json(data)}", flush=True)


def log_http_err(method: str, path: str, detail: str) -> None:
    """\u6253\u5370\u4e00\u6761\u540e\u7aef HTTP \u5931\u8d25\u3002"""
    print(f"[\u540e\u7aefHTTP] \u2717 \u8bf7\u6c42({method}) {path} \u5931\u8d25: {str(detail)[:300]}", flush=True)


def log_receipt(equip: str, receipt: Any) -> None:
    """\u6253\u5370\u5f15\u64ce\u6267\u884c\u56de\u6267 (\u52a8\u4f5c/\u6210\u529f/\u4f4d\u7f6e/\u9ad8\u5ea6\u7b49\u5173\u952e\u5b57\u6bb5; \u4f20 dict \u81ea\u52a8\u6458\u8981, \u5426\u5219\u539f\u6837)\u3002"""
    if isinstance(receipt, dict):
        j = receipt.get("judgment") if isinstance(receipt.get("judgment"), dict) else {}
        pos = receipt.get("position") if isinstance(receipt.get("position"), dict) else {}
        parts = []
        for k, src in (("action", j), ("success", j), ("reason", j), ("altitude_m", j),
                       ("commandType", receipt), ("instruction", receipt), ("isSuccess", receipt)):
            if k in src and src.get(k) not in (None, ""):
                parts.append(f"{k}={src[k]}")
        if pos.get("x") is not None or pos.get("X") is not None:
            parts.append(f"pos=({pos.get('x', pos.get('X'))},{pos.get('y', pos.get('Y'))})")
        print(f"\U0001f4e5 [\u56de\u6267] {equip}  {' '.join(parts) if parts else short_json(receipt, 300)}", flush=True)
    else:
        print(f"\U0001f4e5 [\u56de\u6267] {equip}  {receipt}", flush=True)


def log_vision(agent: str, analysis_type: str, result: Any, *, waited_sec: float | None = None) -> None:
    """\u6253\u5370\u8bc6\u56fe(\u5927\u6a21\u578b)\u5224\u8bfb\u7ed3\u679c \u2014\u2014 \u5173\u952e\u5b57\u6bb5 (\u53ef\u89c1/\u7f6e\u4fe1\u5ea6/\u5bf9\u6b63/\u4e0b\u4e00\u6b65\u52a8\u4f5c/\u504f\u79fb/\u76ee\u6807\u5750\u6807)\u3002

    (\u5b8c\u6574\u7684"\u63d0\u95ee/\u56de\u7b54/\u8017\u65f6"\u5728\u540e\u7aef\u8bc6\u56fe\u65e5\u5fd7 \U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u91cc; \u8fd9\u91cc\u6253\u5370 run_case \u4fa7\u62ff\u5230\u7684\u5224\u8bfb\u7ed3\u8bba\u3002)
    """
    r = result if isinstance(result, dict) else {}
    keys = ("fire_visible", "person_visible", "leak_visible", "target_visible", "reference_matched",
            "task_finished", "status", "confidence", "aligned", "instructionType", "mile", "raw",
            "next_action", "offset_px", "arrived", "obstacle_detected")
    parts = [f"{k}={r[k]}" for k in keys if k in r and r.get(k) not in (None, "")]
    w = f" (\u7b49{waited_sec:.0f}s)" if waited_sec is not None else ""
    print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe] {agent} {analysis_type}{w}: {' '.join(parts) if parts else short_json(r, 300)}", flush=True)


# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
def send_task_complete(client: Any, *, task_id: str, path: str = "/sim/engine/task-complete") -> Any:
    """Notify the engine that a task is complete through the backend.

    The client must implement ``post_json(path, payload, timeout=...)``.
    """
    log_cmd("LJ-ENGINE", f"task-complete  \u901a\u77e5\u5f15\u64ce\u4efb\u52a1\u5b8c\u6210/\u91cd\u542f (taskId={task_id})")
    return client.post_json(path, {"taskId": task_id}, timeout=15.0)


def wait_engine_ready(client: Any, *, task_id: str, engine: str | None = None,
                      command_type: str = "isReady", session_key: str | None = None,
                      timeout_sec: float = 30.0, poll_window: float = 30.0) -> Any:
    """\u4e0b\u53d1\u60f3\u5b9a\u540e, \u7b49\u5f15\u64ce\u91cd\u542f exe \u5e76\u8fd4\u56de\u5c31\u7eea\u72b6\u6001\u518d\u7ee7\u7eed\u4e0b\u53d1\u88c5\u5907\u6307\u4ee4\u3002

    \u5f15\u64ce\u91cd\u542f\u540e\u4f1a\u4e0a\u62a5\u5f62\u5982 ``{"engine":"airsim","isReady":"ready"}`` \u7684\u5c31\u7eea\u62a5\u6587\u3002\u672c\u51fd\u6570\u7ecf\u540e\u53f0
    ``/sim/engine/event/wait`` \u6309 ``commandType`` \u7b49\u5f85\u8be5\u62a5\u6587 (\u9ed8\u8ba4 ``isReady``; \u7528 ``command_type``
    \u6307\u5b9a\u5f15\u64ce\u5b9e\u9645\u7684 commandType)\u3002\u547d\u4e2d ``isReady=="ready"`` (\u82e5\u7ed9\u4e86 ``engine`` \u8fd8\u8981\u5339\u914d) \u5373\u8fd4\u56de\u4e8b\u4ef6\u3002

    \u7a97\u53e3\u5f0f\u7b49\u5f85 + \u5fc3\u8df3; \u5230 ``timeout_sec`` \u4ecd\u6ca1\u7b49\u5230 \u2192 **\u544a\u8b66\u5e76\u653e\u884c (\u8fd4\u56de None)**, \u907f\u514d\u5f15\u64ce\u4e07\u4e00\u4e0d\u53d1\u5c31\u7eea
    \u4fe1\u53f7\u65f6\u628a\u6574\u6279\u5b9e\u9a8c\u5361\u6b7b\u3002\u4efb\u4f55\u5f02\u5e38\u90fd\u4e0d\u629b (\u8fd4\u56de None)\u3002
    """
    import time as _t
    deadline = (_t.time() + timeout_sec) if timeout_sec and timeout_sec > 0 else None
    body: dict[str, Any] = {"commandTypes": [command_type], "timeoutSec": poll_window}
    if session_key:
        body["engineSessionKey"] = session_key
    eng_note = f", engine={engine}" if engine else ""
    print(f"[\u5f15\u64ce] \u5df2\u4e0b\u53d1\u60f3\u5b9a, \u7b49\u5f15\u64ce\u91cd\u542f\u5c31\u7eea (commandType={command_type}{eng_note})...", flush=True)
    
    started = _t.time()
    next_beat = started + max(poll_window, 10.0)
    while True:
        ev = None
        try:
            ev = client.post_json("/sim/engine/event/wait", body, timeout=poll_window + 5.0)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if not ("\u8d85\u65f6" in msg or "timeout" in msg.lower()):
                print(f"[\u5f15\u64ce] \u7b49\u5c31\u7eea\u5f02\u5e38(\u653e\u884c\u7ee7\u7eed): {exc}", flush=True)
                return None
        if isinstance(ev, dict):
            payload: Any = ev
            for k in ("response", "event", "data"):
                if isinstance(ev.get(k), dict):
                    payload = ev[k]; break
            payload = payload if isinstance(payload, dict) else {}
            is_ready = str(payload.get("isReady") or payload.get("ready") or "").strip().lower()
            eng = str(payload.get("engine") or "").strip().lower()
            if is_ready in ("ready", "true", "1") and (engine is None or not eng or eng == str(engine).lower()):
                print(f"[\u5f15\u64ce] \u2705 \u5f15\u64ce\u5c31\u7eea (engine={eng or '?'}, isReady={is_ready}) \u2192 \u5f00\u59cb\u4e0b\u53d1\u88c5\u5907\u52a8\u4f5c\u6307\u4ee4", flush=True)
                return ev
        now = _t.time()
        if now >= next_beat:
            print(f"[\u5f15\u64ce] \u7b49\u5f15\u64ce\u5c31\u7eea... \u5df2\u7b49 {now - started:.0f}s", flush=True)
            next_beat = now + max(poll_window, 10.0)
        if deadline and now >= deadline:
            print(f"[\u5f15\u64ce] \u26a0 {timeout_sec:.0f}s \u5185\u672a\u6536\u5230\u5c31\u7eea\u4fe1\u53f7 (commandType={command_type}? \u662f\u5426\u6b63\u786e)\uff1b\u653e\u884c\u7ee7\u7eed"
                  f"\u2014\u2014\u82e5\u5f15\u64ce\u786e\u5b9e\u672a\u5c31\u7eea\u540e\u7eed\u6307\u4ee4\u4f1a\u5931\u8d25\u3002\u786e\u8ba4\u5c31\u7eea\u62a5\u6587\u7684 commandType \u540e\u7528 --engine-ready-command-type \u6307\u5b9a\u3002",
                  flush=True)
            return None
        _t.sleep(0.5)


def restart_engine_between_episodes(client: Any, *, task_id: str, wait_sec: float = 20.0) -> None:
    """\u6bcf\u8f6e\u5b9e\u9a8c\u4e4b\u95f4: \u8c03 ``/sim/engine/task-complete`` \u91cd\u542f\u5f15\u64ce, \u518d **\u7b49\u5f85 wait_sec \u79d2** \u8ba9\u5f15\u64ce\u91cd\u542f\u5c31\u7eea\u3002

    \u4efb\u4f55\u5f02\u5e38\u90fd\u541e\u6389\u5e76\u7ee7\u7eed (\u4e0d\u8ba9\u91cd\u542f\u5931\u8d25\u4e2d\u65ad\u6574\u6279\u5b9e\u9a8c)\u3002
    """
    print(f"\n{'-' * 60}\n[\u5b9e\u9a8c] \u672c\u8f6e\u7ed3\u675f \u2192 \u91cd\u542f\u5f15\u64ce, \u51c6\u5907\u4e0b\u4e00\u8f6e...", flush=True)
    try:
        send_task_complete(client, task_id=task_id)
        print(f"[\u5f15\u64ce] \u5df2\u8c03\u7528 task-complete (taskId={task_id})", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] task-complete \u8c03\u7528\u5931\u8d25(\u7ee7\u7eed): {exc}", flush=True)
    print(f"[\u5f15\u64ce] \u7b49\u5f85 {wait_sec:.0f}s \u8ba9\u5f15\u64ce\u91cd\u542f\u5c31\u7eea...", flush=True)
    time.sleep(wait_sec)
    print(f"[\u5f15\u64ce] \u5f15\u64ce\u91cd\u542f\u7b49\u5f85\u7ed3\u675f, \u5f00\u59cb\u4e0b\u4e00\u8f6e\u3002\n{'-' * 60}", flush=True)


# --------------------------------------------------------------------------- #




# --------------------------------------------------------------------------- #
def log_frame_pose(results_dir: Any, *, task_id: str, agent: str, step: int, analysis: str,
                   x: float, y: float, alt_m: float, foot_x_cm: float, foot_y_cm: float,
                   img_w: float, img_h: float, pred: Any = None) -> None:
    """\u5728 results/<safe(task_id)>/pose_<analysis>_<safe(agent)>_step_<step>.json \u843d\u4e00\u5e27\u4f4d\u59ff+\u76f8\u673a\u8db3\u5370\u3002

    \u5750\u6807 x/y = \u65e0\u4eba\u673a\u4e16\u754c XY (\u4e0e scenario GT \u540c\u7cfb, UE \u539f\u751f cm); alt_m = \u9ad8\u5ea6(\u7c73, \u53c2\u8003)\u3002
    foot_x_cm/foot_y_cm = \u672c\u5e27\u4fef\u89c6\u56fe\u8986\u76d6\u7684**\u5730\u9762\u8db3\u5370**\u5168\u5bbd/\u5168\u9ad8(cm), \u5df2\u6309\u5404\u4efb\u52a1\u81ea\u8eab\u76f8\u673a\u6a21\u578b\u7b97\u597d
    (\u56fa\u5b9a\u8db3\u5370 topdown_length_m\u00d7width_m, \u6216\u9ad8\u5ea6\u00b7FOV \u8db3\u5370)\u3002metrics \u7528\u5b83\u5224 GT \u662f\u5426\u5728\u753b\u5e45\u5185\u3001\u628a\u50cf\u7d20\u504f\u79fb\u53cd\u7b97\u4e16\u754c\u5750\u6807\u3002
    pred \u53ef\u9009 (run_case \u82e5\u5df2\u7b97\u51fa\u9884\u6d4b\u76ee\u6807 (X,Y))\u3002
    """
    import json as _json
    try:
        d = Path(results_dir) / safe_component(task_id)
        d.mkdir(parents=True, exist_ok=True)
        rec: dict[str, Any] = {
            "agentId": str(agent), "stepIndex": int(step), "analysisType": str(analysis),
            "X": float(x), "Y": float(y), "altitude_m": float(alt_m),
            "foot_x_cm": float(foot_x_cm), "foot_y_cm": float(foot_y_cm),
            "img_w": float(img_w), "img_h": float(img_h),
        }
        if pred is not None:
            try:
                rec["pred"] = {"X": float(pred[0]), "Y": float(pred[1])}
            except Exception:  # noqa: BLE001
                pass
        fname = f"pose_{safe_component(analysis)}_{safe_component(agent)}_step_{int(step)}.json"
        (d / fname).write_text(_json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[\u4f4d\u59ff\u8bb0\u5f55] \u843d\u76d8\u5931\u8d25(\u5ffd\u7565): {exc}", flush=True)
