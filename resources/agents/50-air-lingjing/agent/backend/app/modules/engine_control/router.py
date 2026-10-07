"""HTTP routes for dispatching commands to different LJ-ENGINE adapters."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from app.core.responses import json_success
from app.modules.engine_control import service

router = APIRouter()


async def _json_payload(request: Request) -> dict[str, Any]:
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


@router.post("/sim/engine/command")
async def dispatch_raw_engine_command(request: Request):
    """Dispatch a caller-provided command to one or more LJ-ENGINE sessions."""

    payload = await _json_payload(request)
    command = service.raw_command(payload)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            command,
            default_engine_address=None,
        )
    )


@router.post("/sim/engine/event/wait")
async def wait_engine_event(request: Request):
    """Wait for an inbound LJ-ENGINE event such as carlaSendLoc."""

    return json_success(await service.wait_engine_event(await _json_payload(request)))


@router.post("/sim/engine/scenario")
async def dispatch_engine_scenario(request: Request):
    """Dispatch a caller-provided scenario to one or more LJ-ENGINE sessions."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_scenario_command(payload),
            default_engine_address=None,
            default_require_ack=True,
        )
    )


@router.post("/sim/engine/task-complete")
async def dispatch_task_complete(request: Request):
    """\u5916\u90e8 HTTP \u8c03\u7528 \u2192 \u540e\u53f0\u7ecf WS \u5411 LJ-ENGINE \u4e0b\u53d1"\u4efb\u52a1\u5b8c\u6210"\u4fe1\u606f\u3002

    \u8bf7\u6c42\u4f53: ``{"taskId": "...", \u53ef\u9009 "commandType"(\u9ed8\u8ba4 taskComplete), \u4ee5\u53ca success/result/message \u7b49\u4efb\u52a1
    \u5b8c\u6210\u5b57\u6bb5}``\u3002\u4e0d\u6307\u5b9a ``engineSessionKey`` \u65f6\u9ed8\u8ba4\u5e7f\u64ad\u5230\u6240\u6709\u5df2\u8fde\u63a5\u5f15\u64ce\u4f1a\u8bdd; \u6307\u5b9a\u5219\u53ea\u53d1\u8be5\u4f1a\u8bdd\u3002
    """

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_task_complete_command(payload),
            default_engine_address=None,
        )
    )


@router.post("/sim/engine/airsim/scenario")
async def dispatch_airsim_scenario(request: Request):
    """Dispatch a caller-provided scenario to LJ-ENGINE_airsim."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_scenario_command(payload),
            default_engine_address="airsim",
            default_require_ack=True,
        )
    )


@router.post("/sim/engine/carla/scenario")
async def dispatch_carla_scenario(request: Request):
    """Dispatch a caller-provided scenario to LJ-ENGINE_carla."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_scenario_command(payload),
            default_engine_address="carla",
            default_require_ack=True,
        )
    )


@router.post("/sim/engine/go2/scenario")
async def dispatch_go2_scenario(request: Request):
    """Dispatch a caller-provided scenario to LJ-ENGINE_go2."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_scenario_command(payload),
            default_engine_address="go2",
            default_require_ack=True,
        )
    )


@router.post("/sim/engine/afsim/scenario")
async def dispatch_afsim_scenario(request: Request):
    """Dispatch a caller-provided scenario to LJ-ENGINE_afsim."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_scenario_command(payload),
            default_engine_address="afsim",
            default_require_ack=True,
        )
    )


@router.post("/sim/engine/image/scenario")
async def dispatch_image_scenario(request: Request):
    """Dispatch a caller-provided scenario to LJ-ENGINE_image."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_scenario_command(payload),
            default_engine_address="image",
            default_require_ack=True,
        )
    )


@router.post("/sim/engine/carla/action")
async def dispatch_carla_action(request: Request):
    """Dispatch an unmanned vehicle command to LJ-ENGINE_carla."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_autocar_action(payload),
            default_engine_address="carla",
        )
    )


@router.post("/sim/engine/carla/traffic-jam")
async def dispatch_carla_traffic_jam(request: Request):
    """Dispatch a trafficJam report to LJ-ENGINE_carla."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_carla_traffic_jam(payload),
            default_engine_address="carla",
            default_require_ack=False,
        )
    )


@router.post("/sim/engine/go2/action")
async def dispatch_go2_action(request: Request):
    """Dispatch an unmanned dog command to LJ-ENGINE_go2."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_unmanned_dog_action(payload),
            default_engine_address="go2",
        )
    )


@router.post("/sim/engine/afsim/satellite/action")
async def dispatch_satellite_action(request: Request):
    """Dispatch a satellite command to LJ-ENGINE_afsim."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_satellite_action(payload),
            default_engine_address="afsim",
        )
    )


@router.post("/sim/engine/afsim/ship/action")
async def dispatch_ship_action(request: Request):
    """Dispatch a ship maneuver command to LJ-ENGINE_afsim."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_ship_action(payload),
            default_engine_address="afsim",
        )
    )


@router.post("/sim/engine/image/ship/action")
async def dispatch_image_ship_action(request: Request):
    """Dispatch a ship maneuver command to LJ-ENGINE_image.

    Same shape as ``/sim/engine/afsim/ship/action`` but routed to the image
    engine session (ws ``/ws/LJ-ENGINE/image``). A raw ``command`` body is
    forwarded verbatim; otherwise a shipAction is built from shipId/location.
    """

    payload = await _json_payload(request)
    command = (
        service.raw_command(payload)
        if isinstance(payload.get("command"), dict)
        else service.build_ship_action(payload)
    )
    return json_success(
        await service.dispatch_engine_command(
            payload,
            command,
            default_engine_address="image",
        )
    )


@router.post("/sim/engine/afsim/plane/action")
async def dispatch_plane_action(request: Request):
    """Dispatch an aircraft maneuver command to LJ-ENGINE_afsim."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_plane_action(payload),
            default_engine_address="afsim",
        )
    )


@router.post("/sim/engine/location/request")
async def request_engine_location(request: Request):
    """Dispatch a getEngineLoc command.

    Provide engineAddress/engineSessionKey to target one engine, or omit it to
    broadcast to every connected LJ-ENGINE session.
    """

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_get_engine_loc(payload),
            default_engine_address=None,
            default_require_ack=False,
        )
    )


@router.post("/sim/engine/image/take-photo")
async def take_photo(request: Request):
    """Dispatch takePhoto to LJ-ENGINE_image."""

    payload = await _json_payload(request)
    return json_success(
        await service.dispatch_engine_command(
            payload,
            service.build_take_photo(payload),
            default_engine_address="image",
            default_require_ack=False,
        )
    )
