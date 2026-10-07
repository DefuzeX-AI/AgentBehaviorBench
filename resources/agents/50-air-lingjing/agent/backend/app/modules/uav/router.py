"""HTTP routes for UAV analysis and command compatibility."""

import json
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.core.responses import json_error, json_success
from app.modules.uav import service

router = APIRouter()


async def _json_payload(request: Request) -> dict[str, Any]:
    """Accept JSON even when clients forget the application/json header."""

    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = await request.json()
    except Exception:
        parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("\u8bf7\u6c42\u4f53\u5fc5\u987b\u662f JSON object")
    return parsed


@router.post("/sim/vision/override")
async def set_vision_backbone_override(request: Request):
    """\u767b\u8bb0/\u6e05\u9664\u67d0 taskId \u7684\u8bc6\u56fe backbone \u8986\u76d6 (\u8ba9 run_case \u7528\u547d\u4ee4\u884c\u5207\u8bc6\u56fe\u6a21\u578b, \u4e0d\u6539 .env/\u4e0d\u91cd\u542f)\u3002

    body: ``{taskId?, model?, baseUrl?, apiKey?, apiStyle?}`` \u2014\u2014 \u767b\u8bb0\u8986\u76d6 (taskId \u7701\u7565 \u2192 \u5168\u5c40\u9ed8\u8ba4)\u3002
    ``{taskId?, clear:true}`` \u6216\u7a7a body \u2192 \u6e05\u9664\u8be5 taskId (\u7701\u7565 taskId \u5219\u6e05\u5168\u90e8)\u3002
    """

    from app.modules.ai.service import clear_vision_override, get_vision_override, set_vision_override

    payload = await _json_payload(request)
    task_id = payload.get("taskId") or payload.get("task_id")
    override = {
        "model": payload.get("model"),
        "base_url": payload.get("baseUrl") or payload.get("base_url"),
        "api_key": payload.get("apiKey") or payload.get("api_key"),
        "api_style": payload.get("apiStyle") or payload.get("api_style"),
        "prompt": payload.get("prompt"),   
    }
    has_override = any(str(v or "").strip() for v in override.values())
    if payload.get("clear") or not has_override:
        clear_vision_override(task_id if task_id else None)
        return json_success({"taskId": task_id or "", "cleared": True})
    set_vision_override(task_id, override)
    return json_success({"taskId": task_id or "", "override": get_vision_override(task_id)})


@router.post("/sim/uav/recon")
async def uav_recon(file: UploadFile = File(...)):
    """Legacy multipart endpoint for fire reconnaissance."""

    return json_success(await service.uav_recon(file))


@router.post("/sim/uav/fire/analyze-topdown")
async def analyze_topdown_fire(file: UploadFile = File(...)):
    """Analyze a topdown UAV image and return fire location metadata."""

    return json_success(await service.analyze_topdown_fire(file))


@router.post("/sim/uav/fire/plan")
async def plan_single_drone_fire(
    globalFile: UploadFile = File(...),
    topdownFile: UploadFile = File(...),
    recognition: str = Form("{}"),
):
    """Plan the next single-drone fire-search offset from two images."""

    try:
        recognition_payload = json.loads(recognition) if recognition else {}
    except json.JSONDecodeError as exc:
        return json_error(f"recognition \u5fc5\u987b\u662f JSON \u5b57\u7b26\u4e32: {exc}", status_code=500)
    if not isinstance(recognition_payload, dict):
        return json_error("recognition \u5fc5\u987b\u662f JSON object", status_code=500)
    return json_success(
        await service.plan_single_drone_fire(globalFile, topdownFile, recognition_payload)
    )


@router.post("/sim/uav/fire/report-result")
async def report_fire_result(request: Request):
    """Broadcast fire-recognition result and wait for validation if requested."""

    return json_success(await service.dispatch_fire_recognition_result(await _json_payload(request)))


@router.post("/sim/uav/singlefire")
@router.post("/sim/uav/fire/singlefire")
async def analyze_singlefire(
    globalFile: UploadFile = File(...),
    topdownFile: UploadFile | None = File(None),
    taskId: str = Form(...),
    droneId: str = Form("UAV-FIRE-001"),
    globalLengthM: str = Form("6000"),
    globalWidthM: str = Form("6000"),
    topdownLengthM: str = Form("400"),
    topdownWidthM: str = Form("300"),
):
    """Crop/save singlefire images and analyze them with singledrone_fire/prompt.txt."""

    return json_success(
        await service.analyze_singlefire_images(
            global_file=globalFile,
            topdown_file=topdownFile,
            task_id=taskId,
            drone_id=droneId,
            global_length_m=globalLengthM,
            global_width_m=globalWidthM,
            topdown_length_m=topdownLengthM,
            topdown_width_m=topdownWidthM,
        )
    )


@router.post("/sim/uav/singlefire/result")
@router.post("/sim/uav/fire/singlefire/result")
async def dispatch_singlefire_result(request: Request):
    """Send selected singlefire LLM result fields to UE and AirSim."""

    return json_success(await service.dispatch_singlefire_analysis_result(await _json_payload(request)))


@router.post("/sim/vision/upload")
async def common_vision_upload(request: Request):
    """Common multipart image upload entry for task-specific vision analysis."""

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        return json_error(
            "\u4e0a\u4f20\u56fe\u7247\u5fc5\u987b\u4f7f\u7528 multipart/form-data\uff1b\u56fe\u7247\u5b57\u6bb5\u5fc5\u987b\u662f\u6587\u4ef6\u6d41\uff0c"
            "\u4e0d\u80fd\u76f4\u63a5 POST \u539f\u59cb\u4e8c\u8fdb\u5236\u3001JSON \u6216\u6587\u4ef6\u8def\u5f84\u5b57\u7b26\u4e32\u3002",
            status_code=500,
        )
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001
        return json_error(f"\u89e3\u6790 multipart/form-data \u5931\u8d25: {exc}", status_code=500)

    def field(*names: str, default: str = "") -> str:
        for name in names:
            value = form.get(name)
            if value is not None and not hasattr(value, "filename"):
                return str(value)
        return default

    files = {
        str(key): value
        for key, value in form.items()
        if hasattr(value, "read") and hasattr(value, "filename")
    }
    try:
        return json_success(
            await service.handle_common_vision_upload(
                files=files,
                task_id=field("taskId", "task_id"),
                task_type=field("taskType", "task_type"),
                agent_type=field("agentType", "agent_type"),
                agent_id=field("agentId", "agent_id"),
                view_type=field("viewType", "view_type"),
                analysis_type=field("analysisType", "analysis_type"),
                step_index=field("stepIndex", "step_index", default="0"),
                subtask_index=field("subtaskIndex", "subtask_index", default=""),
                route_point_index=field("routePointIndex", "route_point_index", default=""),
                route_point=field("routePoint", "route_point", default=""),
                global_length_m=field("globalLengthM", "global_length_m", default="6000"),
                global_width_m=field("globalWidthM", "global_width_m", default="6000"),
                topdown_length_m=field("topdownLengthM", "topdown_length_m", default="400"),
                topdown_width_m=field("topdownWidthM", "topdown_width_m", default="300"),
                current_height_m=field("uavHeightM", "currentHeightM", "current_height_m", default=""),
                photoid=field("photoid", "photoId", "photo_id", default=""),
                memo=field("memo", "memory", "subtaskMemo", default=""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return json_error(str(exc) or "\u516c\u7528\u89c6\u89c9\u4e0a\u4f20\u5931\u8d25", status_code=500)


@router.post("/sim/uav/deliverytask/traffic-inspect")
async def analyze_deliverytask_traffic(
    file: UploadFile = File(...),
    taskId: str = Form(...),
    droneId: str = Form("UAV-DELIVERY-001"),
    routePointIndex: str = Form("0"),
    routePoint: str = Form(""),
):
    """Save a deliverytask UAV topdown image and analyze route blockage."""

    return json_success(
        await service.analyze_deliverytask_traffic_image(
            file=file,
            task_id=taskId,
            drone_id=droneId,
            route_point_index=routePointIndex,
            route_point=routePoint,
        )
    )


@router.post("/sim/uav/image/upload")
async def upload_uav_image(request: Request):
    """Save a UAV image for the local singledrone_fire example."""

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        return json_error(
            "\u4e0a\u4f20\u56fe\u7247\u5fc5\u987b\u4f7f\u7528 multipart/form-data\uff1b\u5b57\u6bb5 file \u5fc5\u987b\u662f\u56fe\u7247\u6587\u4ef6\u6d41\uff0c"
            "\u4e0d\u80fd\u76f4\u63a5 POST \u539f\u59cb\u4e8c\u8fdb\u5236\u3001JSON \u6216\u6587\u4ef6\u8def\u5f84\u5b57\u7b26\u4e32\u3002",
            status_code=500,
        )

    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001
        return json_error(f"\u89e3\u6790 multipart/form-data \u5931\u8d25: {exc}", status_code=500)

    file = form.get("file")
    if file is None:
        fields = ", ".join(str(key) for key in form.keys()) or "\u65e0"
        return json_error(
            "\u7f3a\u5c11\u5fc5\u586b\u6587\u4ef6\u5b57\u6bb5 file\u3002\u8bf7\u4f7f\u7528\u5b57\u6bb5\u540d file \u4e0a\u4f20\u56fe\u7247\u6587\u4ef6\u672c\u4f53\uff1b"
            'curl \u793a\u4f8b: -F "file=@topdown.png;type=image/png"\u3002'
            f"\u5f53\u524d\u6536\u5230\u7684\u8868\u5355\u5b57\u6bb5: {fields}",
            status_code=500,
        )
    if not hasattr(file, "read") or not hasattr(file, "filename"):
        return json_error(
            "\u5b57\u6bb5 file \u6536\u5230\u7684\u662f\u666e\u901a\u5b57\u7b26\u4e32\uff0c\u4e0d\u662f\u6587\u4ef6\u3002curl \u4e2d\u5fc5\u987b\u5199 "
            '"file=@\u56fe\u7247\u8def\u5f84"\uff0c\u7a0b\u5e8f\u4e2d\u5fc5\u987b\u4f20 multipart \u6587\u4ef6\u6d41/\u6587\u4ef6\u5bf9\u8c61\u3002',
            status_code=500,
        )

    def field(*names: str, default: str = "") -> str:
        for name in names:
            value = form.get(name)
            if value is not None and not hasattr(value, "filename"):
                return str(value)
        return default

    try:
        data = await service.save_singledrone_fire_image(
            file,
            task_id=field("taskId", "task_id"),
            drone_id=field("droneId", "drone_id", default="UAV-FIRE-001"),
            image_type=field("imageType", "image_type", default="global_rgb"),
            length_m=field("lengthM", "length_m"),
            width_m=field("widthM", "width_m"),
            side_length_m=field("sideLengthM", "side_length_m"),
        )
    except Exception as exc:  # noqa: BLE001
        return json_error(str(exc) or "\u56fe\u7247\u4e0a\u4f20\u5931\u8d25", status_code=500)

    return json_success(data)


@router.post("/sim/uav/airsim/singledrone-fire/scenario")
async def dispatch_singledrone_fire_scenario(request: Request):
    """Dispatch the local singledrone_fire scenario to LJ-ENGINE clients."""

    return json_success(await service.dispatch_singledrone_fire_scenario(await _json_payload(request)))


@router.post("/sim/uav/airsim/action")
async def dispatch_airsim_action(request: Request):
    """Dispatch a raw AirSim executeAction command to LJ-ENGINE clients."""

    return json_success(await service.dispatch_airsim_action(await _json_payload(request)))


@router.post("/sim/uav/airsim/set-destination")
async def dispatch_airsim_set_destination(request: Request):
    """Dispatch an AirSim setDestination command to LJ-ENGINE_airsim."""

    return json_success(await service.dispatch_airsim_set_destination(await _json_payload(request)))


@router.post("/sim/uav/route/plan")
async def uav_route_plan(
    file: UploadFile = File(...),
    mapFile: UploadFile = File(...),
):
    """Legacy multipart endpoint for route planning with map context."""

    return json_success(await service.uav_route_plan(file, mapFile))


@router.post("/sim/uav/takeoff")
async def uav_takeoff(payload: dict[str, Any]):
    """Dispatch a takeoff/control command to realtime clients."""

    await service.uav_takeoff(payload)
    return json_success(None)


@router.post("/sim/command")
async def command(payload: dict[str, Any]):
    """Dispatch an arbitrary command to a target realtime user type."""

    await service.dispatch_command(payload)
    return json_success(None)
