"""SQLAlchemy mappings for the LingJing application database.

Stable business tables live on `Base` and use `data/lingjing.db`.
High-frequency streaming records (`sim_data`) live on `StreamBase` and use
`data/stream.db`, keeping realtime writes separate while still using SQLite.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base, StreamBase

PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    """Shared timestamp columns present on simulation tables."""

    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SimScene(TimestampMixin, Base):
    """Simulation scene definition, mapped from `sim_scene`."""

    __tablename__ = "sim_scene"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scene_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scene_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)


class SimTask(TimestampMixin, Base):
    """Legacy compatibility task table used by the old Java API.

    The current schema models task orchestration through `task_sequence` and
    `task_detail`. This model remains for strict compatibility with existing
    `/sim/task/*` endpoints until those APIs are migrated.
    """

    __tablename__ = "sim_task"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    task_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_code: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    scene_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SimSceneInstance(TimestampMixin, Base):
    """Scene instance JSON/configuration, mapped from `sim_scene_instance`."""

    __tablename__ = "sim_scene_instance"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)


class SimData(TimestampMixin, StreamBase):
    """Realtime simulation data snapshots, stored in the stream SQLite DB."""

    __tablename__ = "sim_data"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)


class FieldMapping(TimestampMixin, Base):
    """Field mapping configuration, mapped from `field_mapping`."""

    __tablename__ = "field_mapping"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    message_type: Mapped[str] = mapped_column(String(100), nullable=False)
    mapping_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True, default="active")


class ServiceInstance(TimestampMixin, Base):
    """Service discovery/heartbeat record, mapped from `service_instance`."""

    __tablename__ = "service_instance"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(100), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SysUser(TimestampMixin, Base):
    """System user table, mapped from `sys_user`."""

    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(100), nullable=False)
    project_code: Mapped[str] = mapped_column(String(100), nullable=False)
    real_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True, default="active")


class TaskDetail(TimestampMixin, Base):
    """Detailed executable task row, mapped from `task_detail`."""

    __tablename__ = "task_detail"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    sequence_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_asset: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_condition: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    depends_on: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timeout_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TaskSequence(TimestampMixin, Base):
    """Task sequence header, mapped from `task_sequence`."""

    __tablename__ = "task_sequence"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="sequential")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    execution_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UavEquipmentInfo(Base):
    """UAV/UGV equipment definition, mapped from `uav_equipment_info`."""

    __tablename__ = "uav_equipment_info"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    uav_scene_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    equipment_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UavSceneInfo(Base):
    """UAV collaboration scenario, mapped from `uav_scene_info`."""

    __tablename__ = "uav_scene_info"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scene_name: Mapped[str] = mapped_column(String(255), nullable=False)
    collaboration_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class City(Base):
    """Legacy optional city record used by previous Java weather APIs."""

    __tablename__ = "hat_city"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    city_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    city_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    father: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class CityWeather(Base):
    """Legacy optional generated weather record used by previous Java APIs."""

    __tablename__ = "city_weather"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    city_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    date: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    weather: Mapped[int | None] = mapped_column(Integer, nullable=True)
