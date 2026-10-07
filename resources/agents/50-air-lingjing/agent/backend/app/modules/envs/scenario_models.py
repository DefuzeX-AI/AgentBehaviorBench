"""User-facing Pydantic models matching the production \u60f3\u5b9a JSON format.

Users define a scenario by instantiating ``ScenarioDefinition``. The model's
serialized form is exactly what gets dispatched over WebSocket to LJ-ENGINE
during environment reset.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    """Position container accepting UE XYZ, lon/lat/alt, or TLE line1/line2."""

    model_config = ConfigDict(extra="allow")

    X: float | None = None
    Y: float | None = None
    Z: float | None = None
    lon: float | None = None
    lat: float | None = None
    alt: float | None = None
    line1: float | None = None
    line2: float | None = None


class DroneEntity(BaseModel):
    """\u65e0\u4eba\u673a\u5b9e\u4f53. ``raw`` is the heading angle as in the legacy JSON."""

    model_config = ConfigDict(extra="allow")

    equipmentCode: str
    name: str
    data: Position
    raw: float | None = None
    sensorType: str | None = None


class UnmannedDogEntity(BaseModel):
    """\u65e0\u4eba\u72d7\u5b9e\u4f53. ``raw`` is the yaw/heading angle (deg), as in DroneEntity/AutoVehicleEntity."""

    model_config = ConfigDict(extra="allow")

    equipmentCode: str
    name: str
    data: Position
    raw: float | None = None


class AutoVehicleEntity(BaseModel):
    """\u65e0\u4eba\u8f66\u5b9e\u4f53."""

    model_config = ConfigDict(extra="allow")

    equipmentCode: str
    name: str
    data: Position
    raw: float | None = None


class SatelliteEntity(BaseModel):
    """\u536b\u661f\u5b9e\u4f53. ``side`` \u6807\u8bb0\u7ea2\u84dd\u65b9."""

    model_config = ConfigDict(extra="allow")

    equipmentCode: str
    name: str
    side: Literal["red", "blue"] | None = None
    data: Position
    sensorType: str | None = None


class ShipEntity(BaseModel):
    """\u8230\u8239\u5b9e\u4f53."""

    model_config = ConfigDict(extra="allow")

    equipmentCode: str
    name: str
    side: Literal["red", "blue"] | None = None
    data: Position
    heading: float | None = None


class PlaneEntity(BaseModel):
    """\u98de\u673a\u5b9e\u4f53."""

    model_config = ConfigDict(extra="allow")

    equipmentCode: str
    name: str
    side: Literal["red", "blue"] | None = None
    data: Position
    heading: float | None = None


class EquipmentList(BaseModel):
    """\u88c5\u5907\u6e05\u5355, \u4e0e LJ-ENGINE \u7aef\u5b57\u6bb5\u4e00\u4e00\u5bf9\u5e94."""

    model_config = ConfigDict(extra="allow")

    droneEntityList: list[DroneEntity] = Field(default_factory=list)
    unmannedDogEntityList: list[UnmannedDogEntity] = Field(default_factory=list)
    autoVehicleEntityList: list[AutoVehicleEntity] = Field(default_factory=list)
    satelliteEntityList: list[SatelliteEntity] = Field(default_factory=list)
    shipEntityList: list[ShipEntity] = Field(default_factory=list)
    planeEntityList: list[PlaneEntity] = Field(default_factory=list)


class GoalPosition(BaseModel):
    model_config = ConfigDict(extra="allow")

    lon: float
    lat: float
    alt: float = 0.0


class InitialState(BaseModel):
    """\u5355\u6761\u4efb\u52a1\u7684\u521d\u59cb\u72b6\u6001."""

    model_config = ConfigDict(extra="allow")

    weather: str = ""
    traffic: str = ""
    goalPosition: GoalPosition | None = None


class TaskMatrixItem(BaseModel):
    """\u4efb\u52a1\u77e9\u9635\u7684\u4e00\u884c (Individual / Group / System)."""

    model_config = ConfigDict(extra="allow")

    taskLevel: Literal["Individual", "Group", "System"]
    task_id: str
    goal: str
    initial_state: InitialState = Field(default_factory=InitialState)


class ScenarioDefinition(BaseModel):
    """\u7528\u6237\u9762\u5bf9\u7684\u60f3\u5b9a\u7c7b, \u4e0e\u751f\u4ea7\u73af\u5883 \u60f3\u5b9ajson \u5b8c\u5168\u4e00\u81f4.

    \u901a\u8fc7 ``to_engine_payload()`` \u5f97\u5230\u7684 dict \u5c31\u662f RealtimeEngineBridge
    \u901a\u8fc7 WebSocket \u53d1\u9001\u7ed9 LJ-ENGINE \u7684\u8f7d\u8377\u3002
    """

    model_config = ConfigDict(extra="allow")

    sceneName: str
    collaborationType: str = ""
    sceneRegion: str = ""
    equipmentList: EquipmentList = Field(default_factory=EquipmentList)
    taskMatrix: list[TaskMatrixItem] = Field(default_factory=list)

    def to_engine_payload(self) -> dict[str, Any]:
        """Serialize into the dict pushed over WebSocket to LJ-ENGINE."""

        return self.model_dump(exclude_none=True)

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)
