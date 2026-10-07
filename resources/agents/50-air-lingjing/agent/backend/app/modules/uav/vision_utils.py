"""\u8bc6\u56fe\u5206\u6790\u7684\u901a\u7528\u5de5\u5177\u7bb1 (task-agnostic).

\u5404\u4efb\u52a1\u7684\u8bc6\u56fe\u4ee3\u7801 (analyzer) \u90fd\u653e\u5728\u81ea\u5df1\u7684\u4efb\u52a1\u76ee\u5f55 ``vision.py`` \u91cc, \u590d\u7528\u672c\u6a21\u5757\u8fd9\u4e9b
\u901a\u7528\u96f6\u4ef6, \u4ece\u800c\u4e0d\u518d\u5f80 ``app/modules/uav/service.py`` \u91cc\u5806\u4efb\u52a1\u4e13\u5c5e\u51fd\u6570\u3002

\u63d0\u4f9b:
* :func:`safe_component`     \u2014\u2014 \u6587\u4ef6\u540d/\u8def\u5f84\u5b89\u5168\u5206\u91cf;
* :func:`pick_file`          \u2014\u2014 \u4ece multipart files \u91cc\u6309\u591a\u4e2a\u5019\u9009\u540d\u6311\u4e00\u4e2a;
* :func:`data_url_from_bytes`\u2014\u2014 bytes \u2192 data URL (\u5582\u591a\u6a21\u6001 LLM);
* :func:`save_image_bytes`   \u2014\u2014 \u6821\u9a8c\u5e76\u843d\u76d8\u4e00\u5f20\u4e0a\u4f20\u56fe\u7247, \u8fd4\u56de\u5143\u4fe1\u606f;
* :func:`write_result_json`  \u2014\u2014 \u628a\u8bc6\u56fe\u7ed3\u679c JSON \u843d\u76d8\u5230\u4efb\u52a1 results \u76ee\u5f55;
* :func:`numeric_pair`       \u2014\u2014 \u89e3\u6790 [x, y] \u6570\u5bf9\u3002
"""

from __future__ import annotations

import base64
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image

_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_SUFFIX_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}


def safe_component(value: str | None, default: str = "item") -> str:
    text = _SAFE_RE.sub("_", str(value or "").strip())
    return (text.strip("._-") or default)[:120]


def pick_file(files: dict[str, UploadFile], *names: str) -> UploadFile | None:
    for name in names:
        if name in files:
            return files[name]
        lower = name.lower()
        for key, value in files.items():
            if key.lower() == lower:
                return value
    return None


def data_url_from_bytes(content: bytes, content_type: str | None) -> str:
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type or 'image/png'};base64,{encoded}"


def numeric_pair(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None


def _format_size(width: int, height: int) -> str:
    return f"{width}x{height}"


def save_image_bytes(
    content: bytes,
    *,
    root: Path,
    task_id: str,
    entity_id: str,
    image_type: str,
    filename: str | None = None,
    content_type: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """\u6821\u9a8c\u56fe\u7247\u5e76\u843d\u76d8\u5230 ``root/<task>/<entity>/<image_type>/``, \u8fd4\u56de\u4fdd\u5b58\u5143\u4fe1\u606f\u3002"""

    if not str(task_id or "").strip():
        raise ValueError("taskId \u4e0d\u80fd\u4e3a\u7a7a")
    if not content:
        raise ValueError("\u6587\u4ef6\u4e0d\u80fd\u4e3a\u7a7a")
    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("image/"):
        raise ValueError(f"\u6587\u4ef6\u7c7b\u578b\u5fc5\u987b\u662f\u56fe\u7247\uff0c\u5f53\u524d\u7c7b\u578b: {normalized_content_type}")
    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        image.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("\u4e0a\u4f20\u6587\u4ef6\u4e0d\u662f\u6709\u6548\u56fe\u7247") from exc

    safe_task = safe_component(task_id, "unknown_task")
    safe_entity = safe_component(entity_id, "agent")
    safe_type = safe_component(image_type, "image")
    suffix = Path(Path(filename or "").name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        suffix = _SUFFIX_BY_CONTENT_TYPE.get(normalized_content_type, ".jpg")

    target_dir = Path(root) / safe_task / safe_entity / safe_type
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    saved_filename = f"{safe_type}_{timestamp}{suffix}"
    target_path = target_dir / saved_filename
    target_path.write_bytes(content)

    info: dict[str, Any] = {
        "taskId": safe_task,
        "entityId": safe_entity,
        "imageType": safe_type,
        "filename": saved_filename,
        "contentType": normalized_content_type or None,
        "width": width,
        "height": height,
        "pixelSize": _format_size(width, height),
        "sizeBytes": len(content),
        "path": str(target_path),
    }
    if repo_root is not None:
        try:
            info["relativePath"] = str(target_path.relative_to(repo_root))
        except ValueError:
            pass
    return info


def write_result_json(
    *,
    results_root: Path,
    kind: str,
    task_id: str,
    payload: dict[str, Any],
) -> Path:
    """\u628a\u8bc6\u56fe\u7ed3\u679c JSON \u843d\u76d8\u5230 ``results_root/<task>/<kind>_<task>_<ts>.json``\u3002

    \u4f1a\u5728 payload \u91cc\u8865\u4e0a ``result_path``; \u6587\u4ef6\u540d\u524d\u7f00 = ``kind`` (\u4f9b run_case \u8f6e\u8be2\u5339\u914d)\u3002
    """

    import json

    safe_task = safe_component(task_id, "unknown_task")
    results_dir = Path(results_root) / safe_task
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = results_dir / f"{kind}_{safe_task}_{timestamp}.json"
    payload = {**payload, "result_path": str(path)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
