"""Enterprise TAMS SQLAlchemy models (PostgreSQL + PostGIS)."""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AssetType(Base):
    __tablename__ = "asset_types"

    asset_type_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    default_parameters: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    assets: Mapped[list["Asset"]] = relationship(back_populates="asset_type")


class Substation(Base):
    __tablename__ = "substations"

    substation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    substation_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    substation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    voltage_level: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="InService")

    assets: Mapped[list["Asset"]] = relationship(back_populates="substation")


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    asset_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type_id: Mapped[int] = mapped_column(ForeignKey("asset_types.asset_type_id"), nullable=False)
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.asset_id"))
    substation_id: Mapped[int | None] = mapped_column(ForeignKey("substations.substation_id"))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    installation_date: Mapped[date | None] = mapped_column(Date)
    warranty_expiry_date: Mapped[date | None] = mapped_column(Date)
    voltage_level_kv: Mapped[float | None] = mapped_column(Float)
    capacity_rating: Mapped[float | None] = mapped_column(Float)
    capacity_unit: Mapped[str | None] = mapped_column(String(20))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="InService")
    criticality: Mapped[str] = mapped_column(String(20), default="Medium")
    qr_code_url: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[list | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    geometry: Mapped[str | None] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    asset_type: Mapped["AssetType"] = relationship(back_populates="assets")
    substation: Mapped["Substation | None"] = relationship(back_populates="assets")
    parent: Mapped["Asset | None"] = relationship(
        remote_side="Asset.asset_id", back_populates="children"
    )
    children: Mapped[list["Asset"]] = relationship(back_populates="parent")
    sensors: Mapped[list["Sensor"]] = relationship(back_populates="asset")
    alarms: Mapped[list["Alarm"]] = relationship(back_populates="asset")
    health_scores: Mapped[list["HealthScore"]] = relationship(back_populates="asset")
    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="asset")
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="asset")

    __table_args__ = (
        Index("ix_assets_status_criticality", "status", "criticality"),
        Index("ix_assets_substation", "substation_id"),
        Index("ix_assets_parent", "parent_asset_id"),
    )


class Sensor(Base):
    __tablename__ = "sensors"

    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.asset_id"), nullable=False)
    sensor_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameter: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    alarm_high_threshold: Mapped[float | None] = mapped_column(Float)
    alarm_low_threshold: Mapped[float | None] = mapped_column(Float)
    protocol: Mapped[str | None] = mapped_column(String(20))
    iot_device_id: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset"] = relationship(back_populates="sensors")


class Alarm(Base):
    __tablename__ = "alarms"

    alarm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.asset_id"), nullable=False)
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sensors.sensor_id"))
    alarm_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Active")
    trigger_value: Mapped[float | None] = mapped_column(Float)
    threshold_value: Mapped[float | None] = mapped_column(Float)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closure_notes: Mapped[str | None] = mapped_column(String(1000))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)

    asset: Mapped["Asset"] = relationship(back_populates="alarms")

    __table_args__ = (Index("ix_alarms_status_severity", "status", "severity", "generated_at"),)


class HealthScore(Base):
    __tablename__ = "health_scores"

    health_score_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.asset_id"), nullable=False)
    health_score: Mapped[float] = mapped_column(Float, nullable=False)
    condition_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    rul_months: Mapped[float | None] = mapped_column(Float)
    age_factor: Mapped[float | None] = mapped_column(Float)
    loading_factor: Mapped[float | None] = mapped_column(Float)
    inspection_factor: Mapped[float | None] = mapped_column(Float)
    failure_history_factor: Mapped[float | None] = mapped_column(Float)
    sensor_health_factor: Mapped[float | None] = mapped_column(Float)
    criticality_factor: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    model_version: Mapped[str | None] = mapped_column(String(20))

    asset: Mapped["Asset"] = relationship(back_populates="health_scores")


class WorkOrder(Base):
    __tablename__ = "work_orders"

    work_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    work_order_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.asset_id"), nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(10), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="Medium")
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    description: Mapped[str | None] = mapped_column(Text)
    assigned_crew: Mapped[str | None] = mapped_column(String(200))
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    actual_cost: Mapped[float | None] = mapped_column(Float)
    labor_hours: Mapped[float | None] = mapped_column(Float)
    root_cause: Mapped[str | None] = mapped_column(String(500))
    completion_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset"] = relationship(back_populates="work_orders")


class Inspection(Base):
    __tablename__ = "inspections"

    inspection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.asset_id"), nullable=False)
    inspection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Scheduled")
    inspector_name: Mapped[str | None] = mapped_column(String(200))
    scheduled_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overall_score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text)
    report_pdf_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset"] = relationship(back_populates="inspections")


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"

    user_role_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.role_id"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "role_id"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_audit_timestamp", "timestamp"),)
