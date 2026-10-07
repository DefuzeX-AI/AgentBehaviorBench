"""\u5355\u65e0\u4eba\u673a"\u533a\u57df\u4f18\u5148 + \u53cc\u89c6\u56fe\u641c\u706b + \u5f15\u64ce\u88c1\u51b3\u706d\u706b"\u8fd0\u884c\u95ed\u73af (\u771f\u673a / \u540e\u7aef HTTP)\u3002

\u95ed\u73af (\u4e25\u683c\u5bf9\u9f50 scenario.py \u7684 workflow, \u5750\u6807\u5355\u4f4d = \u5398\u7c73 cm; \u76f8\u673a FOV=90\u00b0):
  1. \u4e0b\u53d1\u60f3\u5b9a (build_single_drone_fire_scenario) \u2192 \u8d77\u98de (UAV_TAKEOFF_HEIGHT_M);
  2. setDestination **\u5148\u98de\u5230 range_center()** (\u533a\u57df\u4f18\u5148);
  3. \u641c\u706b\u5faa\u73af (\u53d7 --max-steps \u7ea6\u675f):
     - \u62cd\u4fef\u89c6\u56fe (analysisType=firespot_search, \u706b\u60c5\u63cf\u8ff0\u7ecf metadata \u4f20\u7ed9\u8bc6\u56fe);
     - \u4fef\u89c6\u6ca1\u786e\u8ba4\u706b \u2192 \u518d\u62cd\u524d\u89c6\u56fe (firespot_front) \u8054\u5408\u5224\u65ad (\u4eff\u6d77\u8fb9 dual-view);
     - \u770b\u5230\u706b: \u7528 **\u4fef\u89c6\u50cf\u7d20\u504f\u79fb offset_px + \u65e0\u4eba\u673a\u5f53\u524d\u9ad8\u5ea6 (\u5f15\u64ce\u4e0a\u62a5 altitude_m, \u7c73\u2192cm) + FOV** \u53cd\u7b97
       \u706b\u6e90\u4e16\u754c\u5750\u6807 (cm), setDestination \u671d\u706b\u6e90\u98de\u8fd1 (\u76ee\u6807\u5939\u8fdb range_bbox); **\u4e0d\u518d\u7528\u5168\u5c40\u56fe\u5224\u5411**;
     - \u6ca1\u770b\u5230\u706b: \u5728 range \u5185\u86c7\u5f62\u626b\u63cf / \u524d\u79fb\u627e\u706b;
  4. **\u6210\u529f\u5224\u5b9a = \u5f15\u64ce\u88c1\u51b3** (\u65e0\u4eba\u673a\u88c1\u51b3.txt): \u60f3\u5b9a\u4e0b\u53d1\u8fd4\u56de\u521d\u59cb\u8ddd\u79bb\u88c1\u51b3 (action=initialize_scenario);
     \u4e4b\u540e **\u6bcf\u6761\u6307\u4ee4\u5b8c\u6210\u7684 executionCompleted \u56de\u6267\u91cc judgment.success=true \u5373\u706b\u6e90\u4efb\u52a1\u6210\u529f**, \u5426\u5219\u7ee7\u7eed\u4e0b\u6307\u4ee4\u3002
     **\u7edd\u4e0d\u81ea\u5224\u5df2\u706d\u706b**, \u53ea\u8d1f\u8d23\u98de\u5230\u706b\u6e90\u9644\u8fd1 (XY \u8db3\u591f\u8fd1), \u7531\u5f15\u64ce\u88c1\u51b3\u3002max_steps \u515c\u5e95\u3002

\u5730\u9762\u8db3\u5370(cm) = 2 \u00b7 \u9ad8\u5ea6(m) \u00b7 100 \u00b7 tan(FOV/2);  \u504f\u79fb(cm) = (\u50cf\u7d20\u504f\u79fb / \u753b\u5e45\u50cf\u7d20) \u00b7 \u8db3\u5370(cm);
\u706b\u6e90 = \u65e0\u4eba\u673a\u5f53\u524d XY + \u504f\u79fb\u3002

\u7ea6\u675f: \u4e0d\u6539\u65e7\u6587\u4ef6 (run_case.py / run_case_fire.py / engines.py / env.py / evaluator.py)\u3002\u672c\u811a\u672c\u81ea\u5305\u542b,
\u590d\u7528 run_case_test.py \u7684 HttpClient/ensure_sessions/send_takeoff \u7b49\u96f6\u4ef6, \u5176\u4f59 (\u52a8\u4f5c/\u4e8b\u4ef6/\u88c1\u51b3/\u50cf\u7d20\u6362\u7b97)
\u76f4\u63a5\u6284\u6d77\u8fb9 + \u5de5\u4e1a\u56ed\u533a\u72d7\u7684 engine_io \u5b9e\u73b0\u3002

\u5047\u8bbe (\u6807\u6ce8\u4e8e\u6b64):
  * \u88c1\u51b3\u968f\u6bcf\u6761 executionCompleted \u56de\u6267\u7684 judgment.success \u7ed9\u51fa (\u89c1 \u65e0\u4eba\u673a\u88c1\u51b3.txt), \u4e0d\u518d\u5355\u72ec\u8f6e\u8be2\u88c1\u51b3\u4f1a\u8bdd\u3002
  * \u9ad8\u5ea6 altitude_m \u4ece\u56de\u6267\u7684 judgment / position \u91cc\u53d6 (\u65e0\u4eba\u673a\u88c1\u51b3.txt \u4e24\u5904\u90fd\u5e26); \u53d6\u4e0d\u5230\u624d\u56de\u9000 --search-alt-m\u3002
  * \u516c\u7528\u4e0a\u4f20\u8def\u7531\u53ea\u900f\u4f20\u56fa\u5b9a\u8868\u5355\u5b57\u6bb5, \u6545\u706b\u60c5\u63cf\u8ff0\u9ed8\u8ba4\u8d70 scenario \u5e38\u91cf (vision \u5185\u56de\u9000)\u3002
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.envs.task_id import make_task_id
from examples._log_util import (
    setup_console_logging,
    log_cmd,
    brief_cmd,
    restart_engine_between_episodes,
    wait_engine_ready,
    add_backbone_args,
    push_vision_override,
    send_task_complete,
    log_frame_pose,
    log_receipt,
    log_vision,
)
from examples.singledrone_fire import vision as _vision  
from examples.singledrone_fire.run_case_test import (
    HttpClient,
    build_scenario_payload,
    ensure_sessions,
    safe_component,
    send_scenario,
    send_takeoff,
)
from examples.singledrone_fire.scenario import (
    CAM_FOV_DEG,
    UAV_TAKEOFF_HEIGHT_M,
    build_single_drone_fire_scenario,
    fire_description,
    range_bbox,
    range_center,
    uav_id,
)

CASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CASE_DIR / "results"

AIRSIM_SESSION = "LJ-ENGINE_airsim"
IMAGE_SESSION = "LJ-ENGINE_image"
TASK_TYPE = "singledrone_fire"


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def set_uav_destination(client: HttpClient, *, task_id: str, drone_id: str, x: float, y: float,
                        z: float, speed: float, session: str, timeout_sec: float) -> dict[str, Any]:
    """\u65e0\u4eba\u673a\u98de\u5f80\u56fa\u5b9a\u70b9 (setDestination); command \u53ea\u542b x/y/z\u3002\u975e\u963b\u585e\u4e0b\u53d1 + \u963b\u585e\u7b49\u6267\u884c\u56de\u6267\u3002"""
    log_cmd(drone_id, f"setDestination  {brief_cmd({'x': round(x), 'y': round(y), 'z': round(z)})}")
    client.post_json("/sim/uav/airsim/action", {
        "taskId": task_id, "engineSessionKey": session, "broadcast": False, "requireAck": False,
        "waitExecutionCompleted": False,
        "command": {"commandType": "executeAction", "taskId": task_id,
                    "dronesAction": [{"dronesId": drone_id, "instructionType": "setDestination",
                                      "command": {"x": float(x), "y": float(y), "z": float(z)}}]}},
        timeout=15.0)
    return wait_drone_event(client, task_id=task_id, drone_id=drone_id, session=session, timeout_sec=timeout_sec)


def wait_drone_event(client: HttpClient, *, task_id: str, drone_id: str | None, session: str,
                     timeout_sec: float) -> dict[str, Any]:
    """\u7a97\u53e3\u5f0f\u7b49\u67d0\u673a\u7684\u4e0b\u4e00\u6761 executionCompleted \u56de\u6267 (\u542b\u6700\u65b0 position); \u8d85\u65f6\u4e0d\u62a5\u9519, \u6253\u5fc3\u8df3\u7eed\u7b49\u3002"""
    window = timeout_sec if timeout_sec > 0 else 30.0
    filters: dict[str, Any] = {"taskId": task_id}
    if drone_id:
        filters["droneId"] = drone_id
    body = {"taskId": task_id, "engineSessionKey": session,
            "commandTypes": ["executionCompleted"], "timeoutSec": window, "filters": filters}
    waited = 0.0
    max_wait_sec = 900.0   
    while True:
        try:
            ev = client.post_json("/sim/engine/event/wait", body, timeout=window + 5.0)
            st = parse_drone_status(ev)
            log_receipt(drone_id or "\u65e0\u4eba\u673a", st)
            return st
        except RuntimeError as exc:
            if "\u8d85\u65f6" in str(exc) or "timeout" in str(exc).lower():
                waited += window
                if waited >= max_wait_sec:
                    raise RuntimeError(
                        f"\u653e\u5f03\u7b49\u5f85 {drone_id or 'drone'} \u6267\u884c\u56de\u6267 (\u7d2f\u8ba1{waited:.0f}s\u2265\u4e0a\u9650{max_wait_sec:.0f}s, "
                        f"\u5f15\u64ce\u7591\u4f3c\u5230\u4e0d\u4e86\u76ee\u6807\u70b9\u6216\u4e0d\u56de\u62a5)") from exc
                print(f"[\u65e0\u4eba\u673a] \u7b49 {drone_id or 'drone'} \u6267\u884c\u56de\u6267... \u5df2\u7b49 {waited:.0f}s (\u52a8\u4f5c\u53ef\u80fd\u8f83\u6162)", flush=True)
                continue
            raise


def _drone_receipt(reply: Any) -> dict[str, Any]:
    """\u4ece\u4e8b\u4ef6\u4fe1\u5c01\u91cc\u5265\u51fa\u771f\u6b63\u5e26 position/judgment \u7684\u56de\u6267\u4f53 (\u6284\u6d77\u8fb9)\u3002"""
    if not isinstance(reply, dict):
        return {}
    cands: list[dict[str, Any]] = [reply]
    for key in ("executionCompleted", "response", "event", "data", "result"):
        v = reply.get(key)
        if isinstance(v, dict):
            cands.append(v)
            for k2 in ("executionCompleted", "event", "data", "response"):
                if isinstance(v.get(k2), dict):
                    cands.append(v[k2])
    for c in cands:
        if "position" in c or "judgment" in c:
            return c
    for c in cands:
        if c.get("commandType") == "executionCompleted":
            return c
    return reply


def parse_drone_status(reply: Any) -> dict[str, Any]:
    """\u89e3\u6790\u65e0\u4eba\u673a executionCompleted \u56de\u6267 \u2192 {drone_id, success, reason, position:{X,Y,Z}|None, altitude_m, ...}\u3002

    altitude_m: \u4f18\u5148\u53d6\u56de\u6267\u663e\u5f0f\u9ad8\u5ea6\u5b57\u6bb5 (altitude/height/alt, \u5355\u4f4d\u5047\u8bbe\u7c73); \u53d6\u4e0d\u5230\u5219 None
    (\u8c03\u7528\u65b9\u56de\u9000 --search-alt-m)\u3002\u5750\u6807 cm\u3002
    """
    rec = _drone_receipt(reply)
    j = rec.get("judgment") or {}
    pos = rec.get("position") or {}
    did = str(rec.get("droneID") or rec.get("droneId") or pos.get("droneID") or pos.get("droneId") or "")
    x = pos.get("x", pos.get("X")); y = pos.get("y", pos.get("Y")); z = pos.get("z", pos.get("Z"))
    position = None
    if x is not None and y is not None:
        position = {"X": float(x), "Y": float(y), "Z": float(z) if z is not None else None}
    alt = None
    for src in (pos, rec, j):
        for k in ("altitude_m", "altitudeM", "altitude", "height_m", "heightM", "height", "alt"):
            v = src.get(k) if isinstance(src, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                alt = float(v); break
        if alt is not None:
            break
    
    sv = j.get("success")
    if isinstance(sv, str):
        sv = sv.strip().lower() in ("true", "ture", "1", "yes")
    fire_success = sv is True
    return {"drone_id": did, "command_type": rec.get("commandType"),
            "action": j.get("action"), "success": fire_success,
            "reason": j.get("reason"), "position": position, "altitude_m": alt,
            "yaw": pos.get("yaw"), "raw": rec}


def _apply_receipt(pos: dict[str, Any], st: dict[str, Any]) -> None:
    p = st.get("position")
    if p and p.get("X") is not None:
        pos["X"] = float(p["X"]); pos["Y"] = float(p["Y"])
        if p.get("Z") is not None:
            pos["Z"] = float(p["Z"])
    if st.get("altitude_m") is not None:
        pos["altitude_m"] = float(st["altitude_m"])
    if st.get("yaw") is not None:
        pos["yaw"] = st["yaw"]


# --------------------------------------------------------------------------- #




# --------------------------------------------------------------------------- #
def wait_initial_adjudication(client: HttpClient, *, task_id: str, drone_id: str, session: str,
                              timeout_sec: float) -> dict[str, Any] | None:
    """\u60f3\u5b9a\u4e0b\u53d1\u540e\u5f15\u64ce\u8fd4\u56de\u7684\u521d\u59cb\u8ddd\u79bb\u88c1\u51b3 (executionCompleted, action=initialize_scenario)\u3002

    \u6709\u9650\u7b49\u5f85\u4e00\u4e2a\u7a97\u53e3, \u8d85\u65f6\u8fd4\u56de None (\u4ec5\u4fe1\u606f\u6027: \u7ed9\u51fa\u521d\u59cb\u4f4d\u7f6e + \u8ddd\u706b\u60c5\u8ddd\u79bb, \u4e0d\u963b\u585e\u540e\u7eed\u8d77\u98de/\u641c\u706b)\u3002
    """
    window = timeout_sec if timeout_sec > 0 else 15.0
    body = {"taskId": task_id, "engineSessionKey": session, "commandTypes": ["executionCompleted"],
            "timeoutSec": window, "filters": {"taskId": task_id, "droneId": drone_id}}
    try:
        ev = client.post_json("/sim/engine/event/wait", body, timeout=window + 5.0)
        return parse_drone_status(ev)
    except RuntimeError as exc:
        if "\u8d85\u65f6" in str(exc) or "timeout" in str(exc).lower():
            return None
        raise


def _announce_judgment(where: str, st: dict[str, Any]) -> bool:
    """\u6253\u5370\u67d0\u6761\u6307\u4ee4\u56de\u6267\u91cc\u7684\u88c1\u51b3 (success/reason), \u8fd4\u56de\u662f\u5426\u706b\u6e90\u4efb\u52a1\u6210\u529f\u3002"""
    succ = bool(st.get("success"))
    print(f"[\u88c1\u51b3] {where}: success={succ} reason={st.get('reason')} "
          f"altitude_m={st.get('altitude_m')}", flush=True)
    return succ


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def request_photo(client: HttpClient, *, task_id: str, drone_id: str, view_type: str,
                  analysis_type: str, step_index: int, upload_base_url: str, image_session: str,
                  fire_desc: str) -> dict[str, Any]:
    """\u8bf7\u6c42\u65e0\u4eba\u673a\u62cd\u7167 (\u4fef\u89c6/\u524d\u89c6); \u56fe\u7247\u4e0a\u4f20 /sim/vision/upload \u89e6\u53d1\u5bf9\u5e94 analysisType \u8bc6\u56fe\u3002

    \u706b\u60c5\u63cf\u8ff0\u540c\u65f6\u585e\u8fdb fireDescription \u5b57\u6bb5 (\u4e0a\u5c42\u8def\u7531\u82e5\u900f\u4f20\u5219\u8bc6\u56fe\u7528\u4e4b; \u5426\u5219 vision \u56de\u9000 scenario \u5e38\u91cf)\u3002
    """
    upload_url = f"{upload_base_url.rstrip('/')}/sim/vision/upload"
    photo_id = f"{task_id}_{drone_id}_{view_type}_step_{step_index}"
    fields = {"taskId": task_id, "taskType": TASK_TYPE, "agentId": drone_id, "agentType": "uav",
              "viewType": view_type, "analysisType": analysis_type, "stepIndex": step_index,
              "photoid": photo_id, "subtaskIndex": 0, "fireDescription": fire_desc}
    model_item = {"droneId": drone_id, "carId": "", "dogId": "", "viewType": view_type, "photoid": photo_id,
                  "uploadSpec": {"url": upload_url, "method": "POST", "contentType": "multipart/form-data",
                                 "fileField": "file", "fields": fields}}
    log_cmd(image_session, f"take-photo  {view_type}/{analysis_type} (drone={drone_id}, step={step_index})")
    resp = client.post_json("/sim/engine/image/take-photo",
                            {"commandType": "takePhoto", "taskId": task_id, "engineSessionKey": image_session,
                             "modelIdList": [model_item]}, timeout=10.0)
    err = resp.get("error") if isinstance(resp, dict) else None
    if err and ("\u672a\u8fde\u63a5" in str(err) or "image" in str(err).lower()):
        raise RuntimeError(f"\u62cd\u7167\u5931\u8d25: {err} (LJ-ENGINE_image \u672a\u8fde\u63a5, \u65e0\u6cd5\u62cd\u7167\u8bc6\u56fe)")
    return resp


def wait_vision_result(*, task_id: str, drone_id: str, analysis_type: str, step_index: int,
                       requested_at: float, timeout_sec: float) -> dict[str, Any]:
    """\u8f6e\u8be2\u8bc6\u56fe\u7ed3\u679c JSON (\u8bc6\u56fe\u5206\u6790\u5668\u5728 /sim/vision/upload \u540e\u843d\u76d8 results/<task>/)\u3002"""
    deadline = time.time() + timeout_sec
    started = time.time()
    task_dir = RESULTS_DIR / safe_component(task_id)
    prefix = f"{analysis_type}_{safe_component(task_id)}_"
    next_beat = started + 20.0
    while time.time() < deadline:
        if task_dir.exists():
            cands: list[tuple[Path, dict[str, Any]]] = []
            for path in task_dir.glob(f"{prefix}*.json"):
                if path.stat().st_mtime < requested_at - 1.0:
                    continue
                try:
                    import json
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                agent = str(payload.get("agentId") or payload.get("droneId") or "")
                if (payload.get("taskId") in {task_id, safe_component(task_id)}
                        and agent in {drone_id, safe_component(drone_id), ""}
                        and int(payload.get("stepIndex") or 0) == step_index):
                    cands.append((path, payload))
            if cands:
                path, payload = max(cands, key=lambda it: it[0].stat().st_mtime)
                return payload
        if time.time() >= next_beat:
            waited = time.time() - started
            hint = ""
            if waited >= 40.0:
                hint = ("  \u2190 \u957f\u65f6\u95f4\u65e0\u7ed3\u679c, \u591a\u534a\u662f\u540e\u7aef\u672a\u52a0\u8f7d\u8be5\u5206\u6790\u5668(\u65b0\u589e vision.py \u9700\u91cd\u542f\u540e\u7aef: "
                        "./scripts/deploy.sh restart), \u6216\u5f15\u64ce\u672a\u628a\u7167\u7247\u4f20\u5230 /sim/vision/upload")
            print(f"[\u8bc6\u56fe] \u7b49 {drone_id} {analysis_type} \u8bc6\u56fe\u7ed3\u679c... \u5df2\u7b49 {waited:.0f}s; \u76ee\u5f55 {task_dir}{hint}",
                  flush=True)
            next_beat += 20.0
        time.sleep(0.5)
    raise RuntimeError(f"\u7b49\u5f85\u8bc6\u56fe\u7ed3\u679c\u8d85\u65f6 {timeout_sec:.0f}s (analysisType={analysis_type}, "
                       f"agent={drone_id}, step={step_index})")


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def px_offset_to_world(offset_px: Any, *, alt_m: float, fov_deg: float, img_w: float, img_h: float,
                       drone_x: float, drone_y: float) -> tuple[dict[str, float], str]:
    """offset_px=[dx,dy] (dx>0 \u53f3=+X\u4e1c, dy>0 \u4e0b=\u2212Y\u5357) \u2192 \u706b\u6e90\u4e16\u754c XY(cm)\u3002

    \u5730\u9762\u8db3\u5370(cm) = 2\u00b7\u9ad8\u5ea6(m)\u00b7100\u00b7tan(FOV/2); \u504f\u79fb(cm) = (\u50cf\u7d20\u504f\u79fb/\u753b\u5e45) \u00b7 \u8db3\u5370\u3002
    """
    half = math.tan(math.radians(max(1.0, min(179.0, fov_deg)) / 2.0))
    fl_cm = 2.0 * float(alt_m) * 100.0 * half          
    fw_cm = fl_cm * (img_h / img_w)                    
    note = f"\u9ad8\u5ea6{alt_m:.0f}m\u2192\u8db3\u5370\u2248{fl_cm:.0f}\u00d7{fw_cm:.0f}cm"
    pair = vu_numeric_pair(offset_px)
    if pair is None:
        return {"X": drone_x, "Y": drone_y}, note + " (\u65e0\u50cf\u7d20\u504f\u79fb\u2192\u7528\u5f53\u524dXY)"
    dx_px, dy_px = pair
    mx = (dx_px / max(img_w, 1.0)) * fl_cm             
    my = -(dy_px / max(img_h, 1.0)) * fw_cm            
    return {"X": drone_x + mx, "Y": drone_y + my}, note


def vu_numeric_pair(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None


def clamp_to_bbox(x: float, y: float, bbox: dict[str, float]) -> tuple[float, float]:
    return (min(max(x, bbox["x0"]), bbox["x1"]), min(max(y, bbox["y0"]), bbox["y1"]))


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def serpentine_waypoints(bbox: dict[str, float], step_x: float, step_y: float) -> list[dict[str, float]]:
    x0, x1 = float(bbox["x0"]), float(bbox["x1"])
    y0, y1 = float(bbox["y0"]), float(bbox["y1"])
    if x1 < x0: x0, x1 = x1, x0
    if y1 < y0: y0, y1 = y1, y0
    ncol = max(1, math.ceil((x1 - x0) / max(step_x, 1e-6)))
    nrow = max(1, math.ceil((y1 - y0) / max(step_y, 1e-6)))
    xs = [x0 + (k + 0.5) * (x1 - x0) / ncol for k in range(ncol)]
    ys = [y0 + (k + 0.5) * (y1 - y0) / nrow for k in range(nrow)]
    pts: list[dict[str, float]] = []
    for r, yy in enumerate(ys):
        row = xs if r % 2 == 0 else list(reversed(xs))
        pts.extend({"X": round(xx, 1), "Y": round(yy, 1)} for xx in row)
    return pts


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def search_one_shot(client: HttpClient, *, task_id: str, drone_id: str, step_index: int, args: Any,
                    fire_desc: str) -> dict[str, Any]:
    req = time.time()
    request_photo(client, task_id=task_id, drone_id=drone_id, view_type="topdown",
                  analysis_type="firespot_search", step_index=step_index,
                  upload_base_url=args.public_upload_base_url, image_session=args.image_session, fire_desc=fire_desc)
    
    
    try:
        res = wait_vision_result(task_id=task_id, drone_id=drone_id, analysis_type="firespot_search",
                                 step_index=step_index, requested_at=req, timeout_sec=args.vision_timeout_sec)
    except Exception as exc:  # noqa: BLE001
        print(f"[\u65e0\u4eba\u673a] {drone_id} \u4fef\u89c6\u8bc6\u56fe\u8d85\u65f6/\u5f02\u5e38(\u672c\u6b65\u8df3\u8fc7, \u7ee7\u7eed\u641c): {exc}", flush=True)
        return {"fire_seen": False, "vision": {}, "bearing_seen": False, "bearing": "center"}
    v = res.get("result") or {}
    log_vision(drone_id, "firespot_search", v, waited_sec=time.time() - req)
    fire_seen = bool(v.get("fire_visible")) and float(v.get("confidence", 0)) >= args.fire_conf
    print(f"[\u65e0\u4eba\u673a] {drone_id} \u4fef\u89c6\u8bc6\u56fe: \u6709\u706b={fire_seen} conf={v.get('confidence')} "
          f"aligned={v.get('aligned')} offset_px={v.get('offset_px')} reason={v.get('reason')}", flush=True)
    out = {"fire_seen": fire_seen, "vision": v, "bearing_seen": False, "bearing": "center"}
    if fire_seen or not args.dual_view:
        return out
    
    try:
        req2 = time.time()
        request_photo(client, task_id=task_id, drone_id=drone_id, view_type="front",
                      analysis_type="firespot_front", step_index=step_index * 10 + 7,
                      upload_base_url=args.public_upload_base_url, image_session=args.image_session, fire_desc=fire_desc)
        ft = float(args.front_timeout_sec) or min(90.0, float(args.vision_timeout_sec))
        res2 = wait_vision_result(task_id=task_id, drone_id=drone_id, analysis_type="firespot_front",
                                  step_index=step_index * 10 + 7, requested_at=req2, timeout_sec=ft)
        v2 = res2.get("result") or {}
        log_vision(drone_id, "firespot_front", v2, waited_sec=time.time() - req2)
        seen2 = bool(v2.get("fire_visible")) and float(v2.get("confidence", 0)) >= args.fire_conf
        out["bearing_seen"] = seen2
        out["bearing"] = str(v2.get("bearing", "center"))
        if seen2:
            print(f"[\u65e0\u4eba\u673a] {drone_id} \u524d\u89c6\u8bc6\u56fe: \u6709\u706b \u65b9\u4f4d={out['bearing']} conf={v2.get('confidence')}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[\u65e0\u4eba\u673a] {drone_id} \u524d\u89c6\u8bc6\u56fe\u5f02\u5e38(\u5ffd\u7565): {exc}", flush=True)
    return out


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def run_firesearch(client: HttpClient, *, task_id: str, args: Any) -> dict[str, Any]:
    drone_id = args.drone_id
    fov = float(args.cam_fov_deg)
    fire_desc = fire_description()
    bbox = range_bbox()
    center = range_center()
    z_plane = float(center["Z"])
    fallback_alt = float(args.search_alt_m)

    
    scenario = build_scenario_payload(task_id)
    try:
        send_task_complete(client, task_id=task_id)  
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u5148\u53d1 complete \u590d\u4f4d\u5f15\u64ce (taskId={task_id})", flush=True)
    except Exception as _exc:  # noqa: BLE001
        print(f"[\u5f15\u64ce] \u4e0b\u53d1\u60f3\u5b9a\u524d\u7684 complete \u5931\u8d25(\u5ffd\u7565): {_exc}", flush=True)
    send_scenario(client, task_id=task_id, scenario=scenario, airsim_session_key=args.airsim_session,
                  image_session_key=args.image_session, timeout_sec=args.scenario_timeout_sec)
    
    
    wait_engine_ready(client, task_id=task_id, engine="airsim",
                      command_type=args.engine_ready_command_type,
                      timeout_sec=args.engine_ready_timeout_sec)
    init_adj = wait_initial_adjudication(client, task_id=task_id, drone_id=drone_id,
                                         session=args.airsim_session, timeout_sec=args.init_adj_timeout_sec)
    if init_adj is not None:
        _announce_judgment("\u521d\u59cb(\u60f3\u5b9a\u4e0b\u53d1)", init_adj)
    else:
        print(f"[\u88c1\u51b3] \u521d\u59cb(\u60f3\u5b9a\u4e0b\u53d1): {args.init_adj_timeout_sec:.0f}s \u5185\u672a\u6536\u5230\u521d\u59cb\u88c1\u51b3, \u8df3\u8fc7(\u4ec5\u4fe1\u606f\u6027, \u4e0d\u5f71\u54cd\u540e\u7eed)",
              flush=True)
    send_takeoff(client, task_id=task_id, airsim_session_key=args.airsim_session, drone_id=drone_id,
                 height_m=UAV_TAKEOFF_HEIGHT_M, speed=args.uav_step_speed, timeout_sec=args.uav_event_timeout_sec)

    
    pos: dict[str, Any] = {"X": center["X"], "Y": center["Y"], "Z": z_plane, "altitude_m": fallback_alt}
    print(f"[\u65e0\u4eba\u673a] {drone_id} \u2192 \u533a\u57df\u4f18\u5148: \u5148\u98de\u5230 range \u4e2d\u5fc3 ({center['X']:.0f},{center['Y']:.0f})", flush=True)
    st = set_uav_destination(client, task_id=task_id, drone_id=drone_id, x=center["X"], y=center["Y"],
                             z=z_plane, speed=args.uav_step_speed, session=args.airsim_session,
                             timeout_sec=args.uav_event_timeout_sec)
    _apply_receipt(pos, st)
    if _announce_judgment("\u98de\u5230range\u4e2d\u5fc3", st):
        print(f"\n\u2705 [\u6210\u529f] \u5f15\u64ce\u88c1\u51b3\u706b\u6e90\u4efb\u52a1\u6210\u529f (\u98de\u5230range\u4e2d\u5fc3\u5373\u6ee1\u8db3): {st.get('reason')}", flush=True)
        return {"success": True, "steps": 0, "reason": st.get("reason"),
                "final_pos": {"X": pos["X"], "Y": pos["Y"]}, "task_id": task_id}

    
    half = math.tan(math.radians(max(1.0, min(179.0, fov)) / 2.0))
    foot_len = 2.0 * fallback_alt * 100.0 * half
    foot_wid = foot_len * (float(args.img_height) / float(args.img_width))
    overlap = min(0.9, max(0.0, float(args.sweep_overlap)))
    step_x = max(foot_len * (1 - overlap), 1.0); step_y = max(foot_wid * (1 - overlap), 1.0)
    sweep_wps = serpentine_waypoints(bbox, step_x, step_y)
    sweep_i = 0
    print(f"[\u65e0\u4eba\u673a] {drone_id} range \u86c7\u5f62\u9884\u6848: {len(sweep_wps)} \u822a\u70b9 (\u8db3\u5370\u2248{foot_len:.0f}\u00d7{foot_wid:.0f}cm)", flush=True)

    
    for step in range(1, int(args.max_steps) + 1):
        print(f"\n===== \u6b65 {step}/{args.max_steps} @({pos['X']:.0f},{pos['Y']:.0f}) =====", flush=True)
        shot = search_one_shot(client, task_id=task_id, drone_id=drone_id, step_index=step, args=args,
                               fire_desc=fire_desc)

        
        _alt = float(pos.get("altitude_m") or fallback_alt)
        _fl = 2.0 * _alt * 100.0 * math.tan(math.radians(max(1.0, min(179.0, fov)) / 2.0))
        log_frame_pose(RESULTS_DIR, task_id=task_id, agent=drone_id, step=step, analysis="firespot_search",
                       x=float(pos["X"]), y=float(pos["Y"]), alt_m=_alt,
                       foot_x_cm=_fl, foot_y_cm=_fl * (float(args.img_height) / float(args.img_width)),
                       img_w=float(args.img_width), img_h=float(args.img_height))

        if shot["fire_seen"]:
            
            alt_m = float(pos.get("altitude_m") or fallback_alt)
            fire_xy, note = px_offset_to_world(shot["vision"].get("offset_px"), alt_m=alt_m, fov_deg=fov,
                                               img_w=float(args.img_width), img_h=float(args.img_height),
                                               drone_x=float(pos["X"]), drone_y=float(pos["Y"]))
            tx, ty = clamp_to_bbox(fire_xy["X"], fire_xy["Y"], bbox)
            print(f"[\u65e0\u4eba\u673a] {drone_id} \u786e\u8ba4\u706b\u6e90 ({note}) \u2192 \u706b\u6e90\u2248({fire_xy['X']:.0f},{fire_xy['Y']:.0f}) "
                  f"\u5939\u8fdbrange\u2192({tx:.0f},{ty:.0f}); setDestination \u98de\u8fd1 (\u4e0d\u7528\u5168\u5c40\u56fe\u5224\u5411)", flush=True)
            st = set_uav_destination(client, task_id=task_id, drone_id=drone_id, x=tx, y=ty, z=z_plane,
                                     speed=args.uav_step_speed, session=args.airsim_session,
                                     timeout_sec=args.uav_event_timeout_sec)
            _apply_receipt(pos, st)
        else:
            
            if shot["bearing_seen"]:
                print(f"[\u65e0\u4eba\u673a] {drone_id} \u4ec5\u524d\u89c6\u89c1\u706b(\u65b9\u4f4d{shot['bearing']}) \u2192 \u671d\u8be5\u65b9\u4f4d\u63a8\u8fdb", flush=True)
            if sweep_i < len(sweep_wps):
                wp = sweep_wps[sweep_i]; sweep_i += 1
                tx, ty = clamp_to_bbox(wp["X"], wp["Y"], bbox)
            else:
                tx, ty = clamp_to_bbox(pos["X"], pos["Y"] + step_y, bbox)  
            print(f"[\u65e0\u4eba\u673a] {drone_id} \u672a\u786e\u8ba4\u706b \u2192 \u86c7\u5f62\u626b\u63cf\u524d\u5f80 ({tx:.0f},{ty:.0f})", flush=True)
            st = set_uav_destination(client, task_id=task_id, drone_id=drone_id, x=tx, y=ty, z=z_plane,
                                     speed=args.uav_step_speed, session=args.airsim_session,
                                     timeout_sec=args.uav_event_timeout_sec)
            _apply_receipt(pos, st)

        
        if _announce_judgment(f"\u6b65{step}", st):
            print(f"\n\u2705 [\u6210\u529f] \u5f15\u64ce\u88c1\u51b3\u706b\u6e90\u4efb\u52a1\u6210\u529f (step {step}): {st.get('reason')}", flush=True)
            return {"success": True, "steps": step, "reason": st.get("reason"),
                    "final_pos": {"X": pos["X"], "Y": pos["Y"]}, "task_id": task_id}

    print(f"\n\u26a0 [\u515c\u5e95] {args.max_steps} \u6b65\u5185\u5f15\u64ce\u672a\u5224\u706b\u6e90\u4efb\u52a1\u6210\u529f, \u7ed3\u675f (\u672a\u5224\u6210\u529f)", flush=True)
    return {"success": False, "steps": int(args.max_steps), "reason": None,
            "final_pos": {"X": pos["X"], "Y": pos["Y"]}, "task_id": task_id}


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="\u5355\u65e0\u4eba\u673a \u533a\u57df\u4f18\u5148+\u53cc\u89c6\u56fe\u641c\u706b+\u5f15\u64ce\u88c1\u51b3\u706d\u706b \u95ed\u73af")
    p.add_argument("--backend-url", default="http://127.0.0.1:9909")
    p.add_argument("--task-id", default="")
    p.add_argument("--drone-id", default=uav_id())
    p.add_argument("--max-steps", type=int, default=40, help="\u641c\u706b\u5faa\u73af\u4e0a\u9650 (\u515c\u5e95)")
    p.add_argument("--episodes", type=int, default=3, help="\u6b63\u5f0f\u5b9e\u9a8c\u8f6e\u6570 (\u591a\u8f6e\u5faa\u73af, \u6bcf\u8f6e\u72ec\u7acb task_id)")
    p.add_argument("--engine-restart-wait-sec", type=float, default=20.0,
                   help="\u7b2c2\u8f6e\u8d77\u6bcf\u8f6e\u8dd1\u524d\u901a\u77e5\u5f15\u64ce\u91cd\u542f\u5e76\u7b49\u5f85\u7684\u79d2\u6570")
    p.add_argument("--airsim-session", default=AIRSIM_SESSION)
    p.add_argument("--image-session", default=IMAGE_SESSION)
    p.add_argument("--public-upload-base-url", default=None,
                   help="\u5f15\u64ce\u628a\u7167\u7247 POST \u5230\u6b64\u5730\u5740\u7684 /sim/vision/upload; \u7f3a\u7701=\u7528 --backend-url")
    p.add_argument("--scenario-timeout-sec", type=float, default=30.0)
    p.add_argument("--engine-ready-command-type", default="isReady",
                   help="\u7b49\u5f15\u64ce\u91cd\u542f\u5c31\u7eea\u62a5\u6587\u7684 commandType (\u9ed8\u8ba4 isReady)")
    p.add_argument("--engine-ready-timeout-sec", type=float, default=30.0,
                   help="\u7b49\u5f15\u64ce\u91cd\u542f\u5c31\u7eea\u7684\u8d85\u65f6(\u79d2); \u8d85\u65f6\u544a\u8b66\u653e\u884c\u4e0d\u6b7b\u7b49 (\u9ed8\u8ba430)")
    p.add_argument("--init-adj-timeout-sec", type=float, default=8.0,
                   help="\u7b49\u60f3\u5b9a\u4e0b\u53d1\u540e\u7684\u521d\u59cb\u8ddd\u79bb\u88c1\u51b3\u7684\u65f6\u957f(\u79d2); \u4ec5\u4fe1\u606f\u6027, \u77ed\u8d85\u65f6\u5373\u53ef, \u53d6\u4e0d\u5230\u5c31\u8df3\u8fc7(\u4e0d\u62d6\u6162\u8d77\u98de)")
    p.add_argument("--vision-timeout-sec", type=float, default=420.0, help="\u7b49\u4fef\u89c6\u8bc6\u56fe\u7ed3\u679c\u8d85\u65f6")
    p.add_argument("--front-timeout-sec", type=float, default=90.0, help="\u524d\u89c6\u8bc6\u56fe\u7b49\u5f85\u4e0a\u9650; 0=\u7528 vision \u8d85\u65f6")
    p.add_argument("--uav-event-timeout-sec", type=float, default=120.0, help="\u7b49\u65e0\u4eba\u673a\u5355\u6761\u6307\u4ee4\u56de\u6267\u7a97\u53e3(\u79d2)")
    p.add_argument("--cam-fov-deg", type=float, default=CAM_FOV_DEG, help="\u4e0b\u89c6\u76f8\u673a\u89c6\u573a\u89d2(\u5ea6)")
    p.add_argument("--search-alt-m", type=float, default=UAV_TAKEOFF_HEIGHT_M,
                   help="\u56de\u9000\u9ad8\u5ea6(\u7c73): \u5f15\u64ce\u56de\u6267\u6ca1\u62a5\u9ad8\u5ea6\u65f6\u7528\u6b64\u7b97\u8db3\u5370 (\u9ed8\u8ba4=\u8d77\u98de\u9ad8\u5ea6)")
    p.add_argument("--fire-conf", type=float, default=0.5, help="\u5224'\u6709\u706b'\u7684\u7f6e\u4fe1\u5ea6\u9608\u503c")
    p.add_argument("--uav-step-speed", type=float, default=20.0, help="\u65e0\u4eba\u673a\u63a7\u5236\u6307\u4ee4\u901f\u5ea6(15-30)")
    p.add_argument("--img-width", type=float, default=1920.0, help="\u4fef\u89c6\u56fe\u50cf\u7d20\u5bbd (\u50cf\u7d20\u504f\u79fb\u6362\u7b97)")
    p.add_argument("--img-height", type=float, default=1080.0, help="\u4fef\u89c6\u56fe\u50cf\u7d20\u9ad8")
    p.add_argument("--sweep-overlap", type=float, default=0.2, help="\u86c7\u5f62\u76f8\u90bb\u8db3\u5370\u91cd\u53e0\u6bd4\u4f8b(0-0.9)")
    p.add_argument("--dual-view", dest="dual_view", action="store_true", default=True,
                   help="\u4fef\u89c6\u6ca1\u786e\u8ba4\u65f6\u518d\u62cd\u524d\u89c6\u8054\u5408\u5224\u65ad(\u9ed8\u8ba4\u5f00)")
    p.add_argument("--no-dual-view", dest="dual_view", action="store_false", help="\u53ea\u7528\u4fef\u89c6\u56fe")
    p.add_argument("--skip-session-check", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="\u53ea\u9884\u89c8\u60f3\u5b9a/\u53c2\u6570, \u4e0d\u8fde\u5f15\u64ce")
    add_backbone_args(p)   
    return p.parse_args()


def main() -> None:
    args = parse_args()
    log_path = setup_console_logging(RESULTS_DIR, "singledrone_fire")
    print(f"[\u65e5\u5fd7] \u63a7\u5236\u53f0\u65e5\u5fd7\u540c\u65f6\u5199\u5165\u6587\u4ef6: {log_path}", flush=True)
    if not args.public_upload_base_url:
        
        
        try:
            from app.core.config import get_settings
            args.public_upload_base_url = get_settings().vision_upload_base_url or args.backend_url
        except Exception:  # noqa: BLE001
            args.public_upload_base_url = args.backend_url
    print(f"[\u5f15\u64ce] \u62cd\u7167\u4e0a\u4f20\u56de\u8c03: {args.public_upload_base_url}/sim/vision/upload (\u5f15\u64ce\u9700\u80fd\u8bbf\u95ee\u6b64\u5730\u5740)", flush=True)

    task_id = args.task_id or make_task_id(prefix="singledrone_fire_search")
    center = range_center(); bbox = range_bbox()

    if args.dry_run:
        import json
        scenario = build_scenario_payload(task_id)
        preview = {
            "mode": "dry-run", "task_id": task_id, "drone_id": args.drone_id,
            "fire_description": fire_description(),
            "takeoff_height_m": UAV_TAKEOFF_HEIGHT_M, "cam_fov_deg": args.cam_fov_deg,
            "range_center": center, "range_bbox": bbox,
            "search_alt_m": args.search_alt_m, "max_steps": args.max_steps,
            "airsim_session": args.airsim_session, "image_session": args.image_session,
            "upload_base_url": args.public_upload_base_url,
            "scenario_sceneName": scenario.get("sceneName"),
            "scenario_keys": sorted(scenario.keys()),
        }
        print("\n[dry-run] \u4e0d\u8fde\u5f15\u64ce, \u4ec5\u9884\u89c8\u5c06\u4e0b\u53d1\u7684\u60f3\u5b9a/\u53c2\u6570:")
        print(json.dumps(preview, ensure_ascii=False, indent=2, default=str))
        return

    client = HttpClient(args.backend_url)
    push_vision_override(client, args)   
    import json
    episodes = max(1, int(args.episodes))
    base_task_id = args.task_id  
    try:
        if not args.skip_session_check:
            ensure_sessions(client, airsim_session_key=args.airsim_session, image_session_key=args.image_session)
        results: list[dict[str, Any]] = []
        for i in range(1, episodes + 1):
            ep_task_id = (f"{base_task_id}_ep{i}" if base_task_id
                          else make_task_id(prefix="singledrone_fire_search"))
            print(f"\n########## \u7b2c {i}/{episodes} \u8f6e (task_id={ep_task_id}) ##########", flush=True)
            
            if i > 1:
                print(f"[\u5f15\u64ce] \u7b2c {i} \u8f6e\u8dd1\u524d\u91cd\u542f\u5f15\u64ce\u5e76\u7b49\u5f85 {args.engine_restart_wait_sec:.0f}s ...", flush=True)
                restart_engine_between_episodes(client, task_id=ep_task_id,
                                                wait_sec=args.engine_restart_wait_sec)
            try:
                result = run_firesearch(client, task_id=ep_task_id, args=args)
            except Exception as exc:  # noqa: BLE001
                print(f"[\u7b2c{i}\u8f6e] \u5f02\u5e38: {exc.__class__.__name__}: {exc}", flush=True)
                result = {"success": False, "steps": None, "reason": f"{exc.__class__.__name__}: {exc}",
                          "final_pos": None, "task_id": ep_task_id}
            print(f"\n[\u7b2c{i}\u8f6e\u7ed3\u679c] " + json.dumps(result, ensure_ascii=False, default=str), flush=True)
            results.append(result)
            
            if not args.dry_run:
                try:
                    send_task_complete(client, task_id=ep_task_id)
                except Exception as exc:  # noqa: BLE001
                    print(f"[\u5f15\u64ce] \u4e0b\u53d1 complete \u5931\u8d25(\u5ffd\u7565): {exc}", flush=True)

        succ = sum(1 for r in results if r.get("success"))
        print("\n########## \u591a\u8f6e\u6c47\u603b ##########", flush=True)
        for i, r in enumerate(results, 1):
            flag = "\u2705\u6210\u529f" if r.get("success") else "\u274c\u672a\u6210\u529f"
            print(f"  \u7b2c{i}\u8f6e {flag}  steps={r.get('steps')}  task_id={r.get('task_id')}  reason={r.get('reason')}",
                  flush=True)
        rate = succ / len(results) if results else 0.0
        print(f"  \u6210\u529f\u7387: {succ}/{len(results)} = {rate * 100:.0f}%", flush=True)
        print("\n" + json.dumps({"episodes": len(results), "success_count": succ,
                                 "success_rate": rate, "results": results},
                                ensure_ascii=False, indent=2, default=str))
        if succ == 0:
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": exc.__class__.__name__,
                          "error": str(exc), "task_id": base_task_id or task_id}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
