"""HTTP routes for scene, task, instance, and simulation data compatibility."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.responses import json_success
from app.db.models import SimData, SimScene, SimSceneInstance, SimTask
from app.db.session import get_db, get_stream_db
from app.modules.simulation import services

router = APIRouter()

# Routes intentionally keep the old Java paths to avoid frontend changes.


@router.post("/sim/scene/save")
def save_scene(payload: dict[str, Any], db: Session = Depends(get_db)):
    return json_success(services.save_scene(db, payload))


@router.get("/sim/scene/getById")
def get_scene_by_id(id: int = Query(...), db: Session = Depends(get_db)):
    return json_success(services._one_or_error(db, SimScene, "\u4eff\u771f\u573a\u666f\u4e0d\u5b58\u5728", id=id))


@router.get("/sim/scene/getBySceneCode")
def get_scene_by_code(sceneCode: str = Query(...), db: Session = Depends(get_db)):
    return json_success(
        services._one_or_error(db, SimScene, "\u4eff\u771f\u573a\u666f\u4e0d\u5b58\u5728", scene_code=sceneCode)
    )


@router.get("/sim/scene/list")
def list_scenes(db: Session = Depends(get_db)):
    return json_success(db.execute(select(SimScene)).scalars().all())


@router.delete("/sim/scene/deleteBySceneCode")
def delete_scene_by_code(sceneCode: str = Query(...), db: Session = Depends(get_db)):
    services.delete_by_field(db, SimScene, "\u4eff\u771f\u573a\u666f\u4e0d\u5b58\u5728", scene_code=sceneCode)
    return json_success("\u5220\u9664\u6210\u529f")


@router.delete("/sim/scene/deleteById")
def delete_scene_by_id(id: int = Query(...), db: Session = Depends(get_db)):
    services.delete_by_id(db, SimScene, id, "\u4eff\u771f\u573a\u666f\u4e0d\u5b58\u5728")
    return json_success("\u5220\u9664\u6210\u529f")


@router.put("/sim/scene/update")
def update_scene(payload: dict[str, Any], db: Session = Depends(get_db)):
    return json_success(services.update_scene(db, payload))


@router.post("/sim/task/save")
def save_task(payload: dict[str, Any], db: Session = Depends(get_db)):
    return json_success(services.save_task(db, payload))


@router.get("/sim/task/getById")
def get_task_by_id(id: int = Query(...), db: Session = Depends(get_db)):
    return json_success(services._one_or_error(db, SimTask, "\u4eff\u771f\u4efb\u52a1\u4e0d\u5b58\u5728", id=id))


@router.get("/sim/task/getByTaskCode")
def get_task_by_code(taskCode: str = Query(...), db: Session = Depends(get_db)):
    return json_success(services._one_or_error(db, SimTask, "\u4eff\u771f\u4efb\u52a1\u4e0d\u5b58\u5728", task_code=taskCode))


@router.get("/sim/task/list")
def list_tasks(db: Session = Depends(get_db)):
    return json_success(db.execute(select(SimTask)).scalars().all())


@router.get("/sim/task/listBySceneId")
def list_tasks_by_scene(sceneId: int = Query(...), db: Session = Depends(get_db)):
    return json_success(
        db.execute(select(SimTask).where(SimTask.scene_id == sceneId)).scalars().all()
    )


@router.delete("/sim/task/deleteByTaskCode")
def delete_task_by_code(taskCode: str = Query(...), db: Session = Depends(get_db)):
    services.delete_by_field(db, SimTask, "\u4eff\u771f\u4efb\u52a1\u4e0d\u5b58\u5728", task_code=taskCode)
    return json_success("\u5220\u9664\u6210\u529f")


@router.delete("/sim/task/deleteById")
def delete_task_by_id(id: int = Query(...), db: Session = Depends(get_db)):
    services.delete_by_id(db, SimTask, id, "\u4eff\u771f\u4efb\u52a1\u4e0d\u5b58\u5728")
    return json_success("\u5220\u9664\u6210\u529f")


@router.put("/sim/task/update")
def update_task(payload: dict[str, Any], db: Session = Depends(get_db)):
    return json_success(services.update_task(db, payload))


@router.post("/sim/scene/instance/save")
def save_instance(payload: dict[str, Any], db: Session = Depends(get_db)):
    return json_success(services.save_instance(db, payload))


@router.get("/sim/scene/instance/getById")
def get_instance_by_id(id: int = Query(...), db: Session = Depends(get_db)):
    return json_success(
        services._one_or_error(db, SimSceneInstance, "\u4eff\u771f\u573a\u666f\u5b9e\u4f8b\u4e0d\u5b58\u5728", id=id)
    )


@router.get("/sim/scene/instance/listBySceneId")
def list_instances_by_scene(sceneId: int = Query(...), db: Session = Depends(get_db)):
    stmt = (
        select(SimSceneInstance)
        .where(SimSceneInstance.scene_id == sceneId)
        .order_by(SimSceneInstance.create_time.desc())
    )
    return json_success(db.execute(stmt).scalars().all())


@router.get("/sim/scene/instance/list")
def list_instances(db: Session = Depends(get_db)):
    stmt = select(SimSceneInstance).order_by(SimSceneInstance.create_time.desc())
    return json_success(db.execute(stmt).scalars().all())


@router.delete("/sim/scene/instance/deleteById")
def delete_instance_by_id(id: int = Query(...), db: Session = Depends(get_db)):
    services.delete_by_id(db, SimSceneInstance, id, "\u4eff\u771f\u573a\u666f\u5b9e\u4f8b\u4e0d\u5b58\u5728")
    return json_success("\u5220\u9664\u6210\u529f")


@router.delete("/sim/scene/instance/deleteBySceneId")
def delete_instance_by_scene(sceneId: int = Query(...), db: Session = Depends(get_db)):
    db.execute(delete(SimSceneInstance).where(SimSceneInstance.scene_id == sceneId))
    return json_success("\u5220\u9664\u6210\u529f")


@router.put("/sim/scene/instance/update")
def update_instance(payload: dict[str, Any], db: Session = Depends(get_db)):
    return json_success(services.update_instance(db, payload))


@router.post("/sim/data/save")
def save_sim_data(payload: dict[str, Any], db: Session = Depends(get_stream_db)):
    return json_success(services.save_sim_data(db, payload))


@router.get("/sim/data/getById")
def get_sim_data_by_id(id: int = Query(...), db: Session = Depends(get_stream_db)):
    return json_success(services._one_or_error(db, SimData, "\u4eff\u771f\u6570\u636e\u4e0d\u5b58\u5728", id=id))


@router.get("/sim/data/getBySceneId")
def get_sim_data_by_scene(
    sceneId: str = Query(...),
    pageNum: int = Query(1),
    pageSize: int = Query(10),
    db: Session = Depends(get_stream_db),
):
    return json_success(services.get_sim_data_page(db, sceneId, pageNum, pageSize))


@router.get("/sim/data/list")
def list_sim_data(db: Session = Depends(get_stream_db)):
    return json_success(db.execute(select(SimData)).scalars().all())


@router.delete("/sim/data/deleteBySceneId")
def delete_sim_data_by_scene(sceneId: str = Query(...), db: Session = Depends(get_stream_db)):
    services.delete_by_field(db, SimData, "\u4eff\u771f\u6570\u636e\u4e0d\u5b58\u5728", task_id=sceneId)
    return json_success("\u5220\u9664\u6210\u529f")


@router.delete("/sim/data/deleteById")
def delete_sim_data_by_id(id: int = Query(...), db: Session = Depends(get_stream_db)):
    services.delete_by_id(db, SimData, id, "\u4eff\u771f\u6570\u636e\u4e0d\u5b58\u5728")
    return json_success("\u5220\u9664\u6210\u529f")


@router.put("/sim/data/update")
def update_sim_data(payload: dict[str, Any], db: Session = Depends(get_stream_db)):
    return json_success(services.update_sim_data(db, payload))


@router.post("/sim/test/dispatchScenario")
async def test_dispatch_scenario(payload: dict[str, Any]):
    """Test endpoint: reset scenario through RealtimeEngineBridge."""

    return json_success(await services.test_reset_scenario(payload))


@router.post("/sim/test/requestObservation")
async def test_request_observation(payload: dict[str, Any]):
    """Test endpoint: pull observation through RealtimeEngineBridge RPC."""

    return json_success(await services.test_request_observation(payload))


@router.post("/sim/test/dispatchAction")
async def test_dispatch_action(payload: dict[str, Any]):
    """Test endpoint: dispatch action through RealtimeEngineBridge."""

    return json_success(await services.test_dispatch_action(payload))
