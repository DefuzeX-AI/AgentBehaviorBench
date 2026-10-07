"""AI proxy service merged from the old `ai-server-master` project."""

import asyncio
import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.responses import AppError


# --------------------------------------------------------------------------- #






# --------------------------------------------------------------------------- #
_TASK_VISION_OVERRIDES: dict[str, dict[str, str]] = {}
_vision_override_ctx: ContextVar[dict[str, str] | None] = ContextVar("vision_override", default=None)


def set_vision_override(task_id: str | None, override: dict[str, Any]) -> None:
    """\u767b\u8bb0\u67d0 taskId \u7684\u8bc6\u56fe backbone \u8986\u76d6 (taskId \u7701\u7565/\u7a7a \u2192 \u5168\u5c40\u9ed8\u8ba4)\u3002\u7a7a\u5b57\u6bb5\u81ea\u52a8\u4e22\u5f03\u3002"""

    ov = {k: str(v) for k, v in (override or {}).items()
          if k in ("model", "base_url", "api_key", "api_style", "prompt") and str(v or "").strip()}
    _TASK_VISION_OVERRIDES[str(task_id or "").strip()] = ov


def clear_vision_override(task_id: str | None = None) -> None:
    """\u6e05\u9664\u67d0 taskId \u7684\u8986\u76d6 (\u7701\u7565 \u2192 \u6e05\u5168\u90e8)\u3002"""

    if task_id is None:
        _TASK_VISION_OVERRIDES.clear()
    else:
        _TASK_VISION_OVERRIDES.pop(str(task_id).strip(), None)


def get_vision_override(task_id: str | None) -> dict[str, str] | None:
    """\u53d6\u67d0 taskId \u7684\u8986\u76d6: \u5148\u7cbe\u786e\u5339\u914d taskId, \u518d\u56de\u843d\u5168\u5c40\u9ed8\u8ba4("")\u3002"""

    key = str(task_id or "").strip()
    if key and key in _TASK_VISION_OVERRIDES:
        return _TASK_VISION_OVERRIDES[key] or None
    return _TASK_VISION_OVERRIDES.get("") or None


def vision_override_ctx() -> ContextVar[dict[str, str] | None]:
    """\u66b4\u9732 contextvar \u4f9b dispatch \u5c42 set/reset (\u89c1 app.modules.uav.service)\u3002"""

    return _vision_override_ctx


def _effective_vision_cfg(
    settings: Settings, *, model: str | None, base_url: str | None,
    api_key: str | None, api_style: str | None,
) -> tuple[str, str, str, str]:
    """\u89e3\u6790\u751f\u6548\u7684\u8bc6\u56fe\u914d\u7f6e: \u663e\u5f0f\u53c2\u6570 \u2192 contextvar \u8986\u76d6 \u2192 settings\u3002"""

    ctx = _vision_override_ctx.get() or {}

    def pick(param: str | None, key: str, fallback: Any) -> str:
        if param:
            return str(param)
        if ctx.get(key):
            return str(ctx[key])
        return str(fallback or "")

    eff_model = pick(model, "model", settings.ai_analysis_model)
    eff_base = pick(base_url, "base_url", settings.ai_base_url)
    eff_key = pick(api_key, "api_key", settings.ai_api_key)
    eff_style = pick(api_style, "api_style", getattr(settings, "ai_api_style", "") or "anthropic").lower()
    return eff_model, eff_base, eff_key, (eff_style or "anthropic")


DEFAULT_FIRE_PROMPT = (
    '\u4e0a\u56fe\u4e2d\u7740\u706b\u4e86\u5417\uff1fProvide your final the following format: { "result": "true" | "false"}'
)


def read_prompt(prompt_type: str, settings: Settings | None = None) -> str:
    """Load prompt text by legacy type, falling back to the Java default prompt."""

    settings = settings or get_settings()
    file_name = "analysis.txt" if prompt_type == "1" else "route_planning_prompt.txt"
    prompt_path = Path(settings.prompt_dir) / file_name
    try:
        return prompt_path.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_FIRE_PROMPT


def strip_markdown_json(content: str) -> str:
    """Remove model-produced markdown fences before JSON parsing."""

    text = content.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def parse_model_json(content: str) -> dict[str, Any]:
    """Parse AI output that should contain a single JSON object."""

    cleaned = strip_markdown_json(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AppError(f"AI\u8fd4\u56de\u5185\u5bb9\u4e0d\u662f\u6709\u6548JSON: {cleaned}") from exc


def _legacy_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt old `{type,imageBase64}` requests to OpenAI-style vision messages."""

    prompt_type = str(payload.get("type") or "1")
    image_base64 = payload.get("imageBase64") or payload.get("image_base64")
    if not image_base64:
        raise ValueError("imageBase64\u4e0d\u80fd\u4e3a\u7a7a")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": read_prompt(prompt_type)},
                {"type": "image_url", "image_url": {"url": image_base64, "detail": "auto"}},
            ],
        }
    ]




_VISION_MAX_DIM = 1280
_VISION_JPEG_QUALITY = 82


def _downscale_data_url(url: str) -> str:
    """``data:image;base64,...`` \u5927\u56fe \u2192 \u7f29\u5230\u6700\u957f\u8fb9\u2264_VISION_MAX_DIM \u7684 JPEG data URL\u3002\u975e\u56fe/\u5df2\u591f\u5c0f/\u51fa\u9519\u2192\u539f\u6837\u8fd4\u56de\u3002"""

    if not isinstance(url, str) or not url.startswith("data:image"):
        return url
    try:
        import base64 as _b64
        import io as _io

        from PIL import Image

        head, data = url.split(",", 1)
        raw = _b64.b64decode(data)
        im = Image.open(_io.BytesIO(raw))
        already_jpeg = "jpeg" in head or "jpg" in head
        if max(im.size) <= _VISION_MAX_DIM and already_jpeg:
            return url
        im = im.convert("RGB")
        im.thumbnail((_VISION_MAX_DIM, _VISION_MAX_DIM))
        buf = _io.BytesIO()
        im.save(buf, "JPEG", quality=_VISION_JPEG_QUALITY)
        return "data:image/jpeg;base64," + _b64.b64encode(buf.getvalue()).decode()
    except Exception:  
        return url


def _downscale_images_in_messages(messages: list) -> list:
    """\u5c31\u5730\u628a messages \u91cc\u6240\u6709 image_url \u7684\u5927\u56fe\u7f29\u5c0f (anthropic/openai \u4e24\u8def\u90fd\u5728\u8f6c\u6362\u524d\u53d7\u76ca)\u3002"""

    for m in messages:
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for c in m["content"]:
            if not (isinstance(c, dict) and c.get("type") == "image_url"):
                continue
            img = c.get("image_url")
            if isinstance(img, dict) and img.get("url"):
                img["url"] = _downscale_data_url(str(img["url"]))
            elif isinstance(img, str):
                c["image_url"] = _downscale_data_url(img)
    return messages


_USAGE_LOG = Path(__file__).resolve().parents[3] / "logs" / "llm_usage.jsonl"


def _record_llm_usage(data: Any, *, style: str, model: str, chars: int, elapsed_s: float) -> None:
    """\u628a\u4e00\u6b21\u8bc6\u56fe\u5927\u6a21\u578b\u8c03\u7528\u7684 token \u7528\u91cf\u8ffd\u52a0\u5230 logs/llm_usage.jsonl\u3002

    E0 \u5b9e\u9a8c\u4e32\u884c\u6267\u884c, \u6545\u79bb\u7ebf\u6309 e0_master.log \u91cc\u5404\u4efb\u52a1\u7684 START/END \u65f6\u95f4\u7a97\u628a\u8fd9\u4e9b\u7528\u91cf\u5f52\u5c5e\u5230\u5bf9\u5e94\u4efb\u52a1/\u8f6e\u6b21,
    \u4ece\u800c\u8865\u9f50\u5355\u4f53\u4efb\u52a1\u4e0e vision-only \u591a\u4f53\u4efb\u52a1\u7f3a\u5931\u7684 tokens \u5217 (\u8fd9\u4e9b\u4efb\u52a1\u4e0d\u8d70\u5ba2\u6237\u7aef TokenMeter)\u3002
    """
    try:
        u = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(u, dict):
            return
        if style == "anthropic":
            pt = int(u.get("input_tokens") or 0)
            ct = int(u.get("output_tokens") or 0)
        else:
            pt = int(u.get("prompt_tokens") or 0)
            ct = int(u.get("completion_tokens") or 0)
        tt = int(u.get("total_tokens") or (pt + ct))
        from datetime import datetime
        rec = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "model": model, "style": style,
               "prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt,
               "chars": chars, "elapsed_s": round(elapsed_s, 2)}
        _USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


async def analysis(payload: Any, settings: Settings | None = None, *,
                   model: str | None = None, base_url: str | None = None,
                   api_key: str | None = None, api_style: str | None = None) -> str:
    """Forward a legacy or OpenAI-style message payload to the configured LLM.

    \u63a5\u53e3\u98ce\u683c\u7531 ``api_style`` \u51b3\u5b9a (\u9ed8\u8ba4 ``anthropic`` \u2192 /v1/messages; \u4e5f\u53ef ``openai`` \u2192 /chat/completions)\u3002
    model/base_url/api_key/api_style \u672a\u663e\u5f0f\u4f20\u65f6\u6309 **contextvar \u8986\u76d6 \u2192 settings** \u89e3\u6790, \u4ece\u800c\u652f\u6301 run_case
    \u7ecf ``/sim/vision/override`` \u7528\u547d\u4ee4\u884c\u5207\u6362\u8bc6\u56fe backbone (\u4e0d\u6539 .env/\u4e0d\u91cd\u542f)\u3002
    """

    settings = settings or get_settings()
    messages = _legacy_messages(payload) if isinstance(payload, dict) else payload
    if not isinstance(messages, list):
        raise ValueError("messages\u4e0d\u80fd\u4e3a\u7a7a")
    _downscale_images_in_messages(messages)  
    eff_model, eff_base, eff_key, style = _effective_vision_cfg(
        settings, model=model, base_url=base_url, api_key=api_key, api_style=api_style)
    if not eff_key:
        raise AppError("AI_API_KEY\u672a\u914d\u7f6e")

    if style == "anthropic":
        url, body, headers = _anthropic_request(messages, settings,
                                                model=eff_model, base_url=eff_base, api_key=eff_key)
    else:
        url = _chat_completions_url(eff_base)
        body = {"model": eff_model, "messages": messages}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {eff_key}"}

    
    has_img = any(isinstance(m, dict) and isinstance(m.get("content"), list)
                  and any(isinstance(c, dict) and c.get("type") in ("image_url", "image") for c in m["content"])
                  for m in messages)
    prompt_preview = _vision_prompt_preview(messages)
    t0 = _now()
    print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2192 \u8c03\u7528 {eff_model} (\u98ce\u683c={style}, \u542b\u56fe\u7247={has_img}, "
          f"\u6700\u957f{settings.ai_timeout_seconds}s)\u2026", flush=True)
    print(f"   \u2753 \u63d0\u95ee \u2502 {prompt_preview}", flush=True)
    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds, trust_env=False) as client:
            
            
            response = await asyncio.wait_for(
                client.post(url, json=body, headers=headers),
                timeout=settings.ai_timeout_seconds + 15,
            )
    except (httpx.ReadTimeout, asyncio.TimeoutError) as exc:
        print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2717 \u8d85\u65f6 \u23f1{_now() - t0:.1f}s (\u4e0a\u9650{settings.ai_timeout_seconds}s)", flush=True)
        raise AppError(f"AI\u8bc6\u56fe\u8bf7\u6c42\u8d85\u65f6\uff0c\u8d85\u8fc7 {settings.ai_timeout_seconds} \u79d2\u4ecd\u672a\u8fd4\u56de") from exc
    except httpx.RequestError as exc:
        print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2717 \u8bf7\u6c42\u5931\u8d25 \u23f1{_now() - t0:.1f}s: {type(exc).__name__}: {exc}", flush=True)
        raise AppError(f"AI\u8bc6\u56fe\u8bf7\u6c42\u5931\u8d25: {type(exc).__name__}: {exc}") from exc
    if response.status_code >= 400:
        print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2717 HTTP {response.status_code} \u23f1{_now() - t0:.1f}s: {response.text[:300]}", flush=True)
    response.raise_for_status()
    data = response.json()
    if style == "anthropic":
        text = "".join(str(b.get("text", "")) for b in (data.get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "text")
        if not text:
            print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2717 \u54cd\u5e94\u65e0\u6587\u672c\u5757 \u23f1{_now() - t0:.1f}s: {str(data)[:300]}", flush=True)
            raise AppError(f"AI\u54cd\u5e94\u683c\u5f0f\u5f02\u5e38: {data}")
        print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2190 \u8fd4\u56de \u23f1{_now() - t0:.1f}s \u00b7 {len(text)}\u5b57\u7b26\n   \u2705 \u56de\u7b54 \u2502 {_clip(text, 300)}", flush=True)
        _record_llm_usage(data, style="anthropic", model=eff_model, chars=len(text), elapsed_s=_now() - t0)
        return text
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2717 \u54cd\u5e94\u683c\u5f0f\u5f02\u5e38 \u23f1{_now() - t0:.1f}s: {str(data)[:300]}", flush=True)
        raise AppError(f"AI\u54cd\u5e94\u683c\u5f0f\u5f02\u5e38: {data}") from exc
    print(f"\U0001f5bc\ufe0f [\u8bc6\u56fe\u5927\u6a21\u578b] \u2190 \u8fd4\u56de \u23f1{_now() - t0:.1f}s \u00b7 {len(text)}\u5b57\u7b26\n   \u2705 \u56de\u7b54 \u2502 {_clip(text, 300)}", flush=True)
    _record_llm_usage(data, style=style, model=eff_model, chars=len(text), elapsed_s=_now() - t0)
    return text


def _now() -> float:
    import time
    return time.time()


def _clip(text: str, limit: int) -> str:
    one = " ".join((text or "").split())
    return one if len(one) <= limit else one[:limit] + " \u2026"


def _vision_prompt_preview(messages: list[dict[str, Any]]) -> str:
    """\u63d0\u53d6 prompt \u7684\u6587\u672c\u90e8\u5206\u505a\u9884\u89c8 (\u56fe\u7247\u4ee5 <\u56fe\u7247> \u5360\u4f4d)\u3002"""
    parts: list[str] = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for x in c:
                if isinstance(x, dict):
                    if x.get("type") == "text":
                        parts.append(str(x.get("text", "")))
                    elif x.get("type") in ("image_url", "image"):
                        parts.append("<\u56fe\u7247>")
    return _clip(" ".join(parts), 220)


def _chat_completions_url(base_url: str) -> str:
    url = str(base_url or "").rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


def _messages_url(base_url: str) -> str:
    """\u5f52\u4e00\u6210 Anthropic /v1/messages \u5168\u5730\u5740 (\u517c\u5bb9\u6839\u57df\u540d / .../v1 / \u5df2\u5e26 /messages)\u3002"""
    url = str(base_url or "").rstrip("/")
    if url.endswith("/messages"):
        return url
    if url.endswith("/v1"):
        return f"{url}/messages"
    return f"{url}/v1/messages"


def _anthropic_image_block(url: str) -> dict[str, Any]:
    if url.startswith("data:"):
        try:
            head, data = url.split(",", 1)
            media = head[5:].split(";", 1)[0] or "image/jpeg"
            return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
        except ValueError:
            pass
    return {"type": "image", "source": {"type": "url", "url": url}}


def _anthropic_request(messages: list[dict[str, Any]], settings: Settings, *,
                       model: str | None = None, base_url: str | None = None,
                       api_key: str | None = None) -> tuple[str, dict[str, Any], dict[str, str]]:
    """OpenAI \u98ce\u683c messages \u2192 Anthropic /v1/messages \u8bf7\u6c42 (url, body, headers)\u3002\u6587\u672c+\u56fe\u7247\u90fd\u8f6c\u3002"""

    sys_parts: list[str] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content")
        if role == "system":
            if isinstance(content, str):
                sys_parts.append(content)
            elif isinstance(content, list):
                sys_parts.extend(str(c.get("text", "")) for c in content
                                 if isinstance(c, dict) and c.get("type") == "text")
            continue
        blocks: list[dict[str, Any]] = []
        if isinstance(content, str):
            blocks.append({"type": "text", "text": content})
        elif isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    blocks.append({"type": "text", "text": str(c.get("text", ""))})
                elif c.get("type") == "image_url":
                    img = c.get("image_url")
                    img_url = img.get("url") if isinstance(img, dict) else img
                    if img_url:
                        blocks.append(_anthropic_image_block(str(img_url)))
        out.append({"role": "assistant" if role == "assistant" else "user",
                    "content": blocks or [{"type": "text", "text": ""}]})
    
    eff_model = model or settings.ai_analysis_model
    eff_key = api_key or settings.ai_api_key
    eff_base = base_url or settings.ai_base_url
    body: dict[str, Any] = {"model": eff_model, "max_tokens": 2048,
                            "messages": out, "thinking": {"type": "disabled"}}
    system = "\n".join(p for p in sys_parts if p)
    if system:
        body["system"] = system
    headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01",
               "Authorization": f"Bearer {eff_key}", "x-api-key": eff_key}
    return _messages_url(eff_base), body, headers
