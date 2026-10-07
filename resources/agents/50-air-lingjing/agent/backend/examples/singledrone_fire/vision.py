"""Single-UAV firefighting vision analyzer: top-down/front dual views to find the fire source per a "fire description".

* ``firespot_search`` \u2014\u2014 UAV top-down view: whether there is a fire source in the frame (flames/heavy smoke/white gymnasium building) + the fire's pixel offset
  relative to the frame center + whether already aligned + a suggested next action. Used by run_case to back-compute the fire source's world coordinates from pixel offset + UAV altitude + FOV.
* ``firespot_front`` \u2014\u2014 UAV front view: whether there is a fire source ahead + approximate bearing (left/center/right). Complements the top-down view,
  widening the detection range (modeled on the seaside rescue_front).

Self-registers via :func:`app.modules.uav.analyzer_registry.register`; results are written to disk at results/<task>/ for run_case to poll.
The true coordinates of the fire are hidden from the agent -- vision only returns "fire present or not + confidence + pixel offset/bearing + next action". Downscale the image to <=1024 before sending to prevent timeouts.

Fire-description clue (what kind of fire to look for): by default taken from this task's scenario.fire_description(); it can also be overridden by the caller via
``metadata['fireDescription']`` (assumption: the shared upload route only passes through fixed fields, so the description defaults to the scenario constant,
not relying on extra form fields; if an upper layer explicitly stuffs it into metadata, that takes priority).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.modules.ai.service import analysis as ai_analysis
from app.modules.ai.service import parse_model_json
from app.modules.uav import vision_utils as vu
from app.modules.uav.analyzer_registry import register

from examples.singledrone_fire.scenario import fire_description, uav_id

CASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CASE_DIR.parents[1]
UPLOAD_ROOT = CASE_DIR / "uploads"
RESULTS_ROOT = CASE_DIR / "results"

DEFAULT_DRONE_ID = uav_id()

_UAV_SYN = {"forward": "forward", "ahead": "forward", "backword": "backword", "backward": "backword", "back": "backword",
            "left": "left", "turn_left": "left", "right": "right", "turn_right": "right",
            "down": "down", "descend": "down", "up": "up", "ascend": "up",
            "setdestination": "setDestination", "goto": "setDestination",
            "stop": "stop", "hover": "stop", "hold": "stop", "none": "stop", "wait": "stop"}


SEARCH_PROMPT_TMPL = """<Role>
You are the perception + flight controller of a wildfire-search UAV flying over a search area, looking
for a FIRE SOURCE that matches a given description.
</Role>
<Fire description (what to look for)>
{fire_desc}
</Fire description>
<Task>
You see ONE top-down image of the search area. (1) Decide whether a fire source matching the description
is visible (open flames / heavy smoke plume / the described white gymnasium building on fire / glowing
embers). (2) DIRECT the UAV's single next move to fly directly OVER that fire source so it can be
extinguished. When the fire is roughly centered below, set aligned=true and action "stop".
</Task>
<UAV actions> (choose ONE)
- "forward"/"backword" : translate toward top/bottom of image -> {{"mile": meters, "speed":15-30}}
- "left"/"right"       : turn so the fire moves toward image center -> {{"raw": degrees, "speed":15-30}}
- "down"               : descend to look closer -> {{"mile": meters, "speed":15-30}}
- "stop"               : hold (fire centered / aligned, or no fire)
</UAV actions>
<Output> Return ONLY JSON:
{{"fire_visible": true|false, "confidence": 0.0-1.0, "aligned": true|false, "offset_px":[dx,dy]|null,
 "next_action": {{"instructionType":"forward|backword|left|right|down|stop","mile":<m>,"raw":<deg>,"speed":<15-30>}},
 "reason":"<short>"}}
</Output>
<Rules>
- offset_px from image center: dx>0 fire is to the RIGHT, dy>0 fire is BELOW center (screen-y down).
- If the fire is roughly centered, aligned=true, action "stop".
- If NO matching fire: fire_visible=false, aligned=false, action "forward" with a modest mile to keep covering the area.
- Plain ground / shadows / roads / non-burning buildings are NOT a fire source.
- Output JSON only.
</Rules>"""


FRONT_PROMPT_TMPL = """<Role>
You are the perception system of a wildfire-search UAV. You see ONE FRONT/oblique camera image looking
ahead over the search area (not straight down).
</Role>
<Fire description (what to look for)>
{fire_desc}
</Fire description>
<Task>
Decide whether a FIRE SOURCE matching the description is visible anywhere ahead (open flames / heavy smoke
plume / the described white gymnasium building on fire). If yes, say roughly where in the frame: left,
center or right. This front view complements the down-looking camera by spotting fire AHEAD of the UAV.
</Task>
<Output> Return ONLY JSON:
{{"fire_visible": true|false, "confidence": 0.0-1.0, "bearing": "left|center|right", "reason":"<short>"}}
</Output>
<Rules>
- Plain ground / sky / clouds / non-burning buildings are NOT a fire source.
- If nothing matches: fire_visible=false, bearing="center".
- Output JSON only.
</Rules>"""


def _resolve_fire_desc(metadata: dict[str, Any] | None) -> str:
    """Fire-finding clue: explicit metadata override > scenario default description."""
    if isinstance(metadata, dict):
        for k in ("fireDescription", "fire_description", "targetDescription", "target_description"):
            v = metadata.get(k)
            if v:
                return str(v)
    return fire_description()


def _num(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError:
                continue
    return None


def _normalize_uav_action(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = {"instructionType": raw}
    if not isinstance(raw, dict):
        return {"instructionType": "stop", "speed": 20.0}
    key = str(raw.get("instructionType") or raw.get("action") or raw.get("type") or "").strip().lower().replace(" ", "_").replace("-", "_")
    it = _UAV_SYN.get(key)
    if it is None:
        return {"instructionType": "stop", "speed": 20.0}
    out: dict[str, Any] = {"instructionType": it}
    if it in ("forward", "backword", "down", "up"):
        out["mile"] = max(0.0, _num(raw, "mile", "distance", "meters", "m") or 0.0)
    elif it in ("left", "right"):
        out["raw"] = (_num(raw, "raw", "angle", "degrees", "deg") or 0.0) % 360.0
    elif it == "setDestination":
        out["x"] = _num(raw, "x", "X"); out["y"] = _num(raw, "y", "Y"); out["z"] = _num(raw, "z", "Z")
    sp = _num(raw, "speed", "spd")
    out["speed"] = min(30.0, max(15.0, sp)) if sp is not None else 20.0
    return out


def _clamp01(v: Any) -> float:
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _validate_search(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError(f"firespot_search output must be a JSON object: {result}")
    act = _normalize_uav_action(result.get("next_action") or result.get("action"))
    vis = result.get("fire_visible")
    if isinstance(vis, str):
        vis = vis.strip().lower() in ("true", "yes", "1")
    return {"fire_visible": bool(vis), "confidence": _clamp01(result.get("confidence", 1.0)),
            "aligned": bool(result.get("aligned")) or act.get("instructionType") == "stop",
            "offset_px": vu.numeric_pair(result.get("offset_px")), "next_action": act,
            "reason": str(result.get("reason", ""))}


def _validate_front(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError(f"firespot_front output must be a JSON object: {result}")
    vis = result.get("fire_visible")
    if isinstance(vis, str):
        vis = vis.strip().lower() in ("true", "yes", "1")
    b = str(result.get("bearing", "center")).strip().lower()
    if b not in ("left", "center", "right"):
        b = "center"
    return {"fire_visible": bool(vis), "confidence": _clamp01(result.get("confidence", 1.0)),
            "bearing": b, "reason": str(result.get("reason", ""))}


def _downscale_for_llm(content: bytes, *, max_side: int = 1024, quality: int = 80) -> tuple[bytes, str]:
    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:  # noqa: BLE001
        return content, "image/jpeg"
    w, h = im.size
    scale = max_side / max(w, h)
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue(), "image/jpeg"


async def _analyze(*, prompt: str, validate, files: dict[str, Any], pick: tuple[str, ...],
                   image_type: str, kind: str, must_have: str, task_id: str, agent_id: str,
                   step_index: Any, metadata: dict[str, Any] | None) -> dict[str, Any]:
    file = vu.pick_file(files, *pick)
    if file is None:
        raise ValueError(must_have)
    content = await file.read()
    saved = vu.save_image_bytes(content, root=UPLOAD_ROOT, task_id=task_id, entity_id=agent_id,
                                image_type=image_type, filename=file.filename,
                                content_type=file.content_type, repo_root=REPO_ROOT)
    llm_bytes, llm_ct = _downscale_for_llm(content)
    print(f"[vision] {agent_id} raw image {len(content)//1024}KB -> compressed {len(llm_bytes)//1024}KB sent to vision LLM ({kind})",
          flush=True)
    parts = [{"type": "text", "text": prompt},
             {"type": "image_url", "image_url": {"url": vu.data_url_from_bytes(llm_bytes, llm_ct), "detail": "high"}}]
    raw = await ai_analysis([{"role": "user", "content": parts}])
    result = validate(parse_model_json(raw))
    safe_agent = vu.safe_component(agent_id, agent_id)
    path = vu.write_result_json(results_root=RESULTS_ROOT, kind=kind, task_id=task_id,
                                payload={"type": kind, "taskId": vu.safe_component(task_id, "unknown_task"),
                                         "agentId": safe_agent, "droneId": safe_agent,
                                         "stepIndex": int(step_index or 0), "result": result,
                                         "raw_response": raw, "savedImage": saved})
    return {"status": "analyzed", "metadata": metadata, "taskId": vu.safe_component(task_id, "unknown_task"),
            "droneId": safe_agent, "savedImage": saved, "result": result, "raw_response": raw,
            "result_path": str(path)}


@register("firespot_search")
async def firespot_search(*, files: dict[str, Any], task_id: str, agent_id: str = DEFAULT_DRONE_ID,
                          step_index: Any = 0, metadata: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
    """UAV top-down vision: per the fire description, decide whether there is a fire source in the frame + pixel offset + next action (fly directly above the fire source)."""
    prompt = SEARCH_PROMPT_TMPL.format(fire_desc=_resolve_fire_desc(metadata))
    return await _analyze(prompt=prompt, validate=_validate_search, files=files,
                          pick=("topdownFile", "topdown", "file"), image_type="topdown",
                          kind="firespot_search", must_have="firespot_search requires uploading topdownFile/topdown/file",
                          task_id=task_id, agent_id=agent_id, step_index=step_index, metadata=metadata)


@register("firespot_front")
async def firespot_front(*, files: dict[str, Any], task_id: str, agent_id: str = DEFAULT_DRONE_ID,
                         step_index: Any = 0, metadata: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
    """UAV front-view vision: whether there is a fire source ahead + approximate bearing (left/center/right). Complements the top-down view to widen the detection range."""
    prompt = FRONT_PROMPT_TMPL.format(fire_desc=_resolve_fire_desc(metadata))
    return await _analyze(prompt=prompt, validate=_validate_front, files=files,
                          pick=("frontFile", "front", "file"), image_type="front",
                          kind="firespot_front", must_have="firespot_front requires uploading frontFile/front/file",
                          task_id=task_id, agent_id=agent_id, step_index=step_index, metadata=metadata)
