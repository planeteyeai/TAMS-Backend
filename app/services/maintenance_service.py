"""Maintenance and work order service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import is_db_ready
from app.models import Asset, WorkOrder
from app.services.mock_data import MOCK_ASSETS


def _seed_mock_work_orders() -> None:
    if _MOCK_WORK_ORDERS:
        return
    templates = [
        {
            "maintenance_type": "CM",
            "priority": "Critical",
            "status": "InProgress",
            "description": "Phase B Bushing Replacement",
            "assigned_crew": "Crew Alpha (HV)",
            "progress_pct": 75,
        },
        {
            "maintenance_type": "PM",
            "priority": "High",
            "status": "Scheduled",
            "description": "Conductor Clearance Trim",
            "assigned_crew": "Crew Delta (ROW)",
            "progress_pct": 30,
        },
        {
            "maintenance_type": "PdM",
            "priority": "Medium",
            "status": "Assigned",
            "description": "Tower Foundation Seal",
            "assigned_crew": "Crew Gamma",
            "progress_pct": 85,
        },
    ]
    for i, tpl in enumerate(templates):
        asset = MOCK_ASSETS[i % len(MOCK_ASSETS)]
        _MOCK_WORK_ORDERS.append(
            {
                "work_order_id": str(uuid4()),
                "id": str(uuid4()),
                "work_order_number": f"WO-2026-{8041 + i}",
                "asset_id": asset["id"],
                "asset_code": asset.get("name", asset["id"]),
                **tpl,
                "created_at": datetime.now(timezone.utc),
            }
        )


def _wo_to_dict(wo: WorkOrder) -> dict:
    return {
        "work_order_id": str(wo.work_order_id),
        "id": str(wo.work_order_id),
        "work_order_number": wo.work_order_number,
        "asset_id": str(wo.asset_id),
        "asset_code": wo.asset.asset_code if wo.asset else None,
        "maintenance_type": wo.maintenance_type,
        "priority": wo.priority,
        "status": wo.status,
        "description": wo.description,
        "assigned_crew": wo.assigned_crew,
        "scheduled_start": wo.scheduled_start,
        "scheduled_end": wo.scheduled_end,
        "actual_start": wo.actual_start,
        "actual_end": wo.actual_end,
        "estimated_cost": wo.estimated_cost,
        "actual_cost": wo.actual_cost,
        "created_at": wo.created_at,
    }


_MOCK_WORK_ORDERS: list[dict] = []


async def list_work_orders(
    session: AsyncSession | None,
    *,
    status: str | None = None,
    maintenance_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    if not is_db_ready() or session is None:
        _seed_mock_work_orders()
        items = _MOCK_WORK_ORDERS
        if status:
            items = [w for w in items if w.get("status") == status]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    stmt = select(WorkOrder).options(selectinload(WorkOrder.asset))
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    if maintenance_type:
        stmt = stmt.where(WorkOrder.maintenance_type == maintenance_type)

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(WorkOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.scalars(stmt)).all()
    return [_wo_to_dict(r) for r in rows], int(total or 0)


async def create_work_order(session: AsyncSession | None, payload: dict) -> dict:
    if not is_db_ready() or session is None:
        wo = {
            "work_order_id": str(uuid4()),
            "id": str(uuid4()),
            "work_order_number": f"WO-MOCK-{len(_MOCK_WORK_ORDERS) + 1}",
            **payload,
            "status": payload.get("status", "Draft"),
            "created_at": datetime.now(timezone.utc),
        }
        _MOCK_WORK_ORDERS.append(wo)
        return wo

    count = await session.scalar(select(func.count()).select_from(WorkOrder)) or 0
    wo = WorkOrder(
        work_order_number=f"WO-2026-{1000 + count}",
        asset_id=UUID(payload["asset_id"]),
        maintenance_type=payload["maintenance_type"],
        priority=payload.get("priority", "Medium"),
        status=payload.get("status", "Draft"),
        description=payload.get("description"),
        assigned_crew=payload.get("assigned_crew"),
        scheduled_start=payload.get("scheduled_start"),
        scheduled_end=payload.get("scheduled_end"),
        estimated_cost=payload.get("estimated_cost"),
    )
    session.add(wo)
    await session.commit()
    await session.refresh(wo, ["asset"])
    return _wo_to_dict(wo)


async def get_work_order(session: AsyncSession | None, work_order_id: str) -> dict | None:
    if not is_db_ready() or session is None:
        return next((w for w in _MOCK_WORK_ORDERS if w.get("work_order_id") == work_order_id or w.get("id") == work_order_id), None)

    try:
        uid = UUID(work_order_id)
    except ValueError:
        return None

    wo = await session.scalar(
        select(WorkOrder).options(selectinload(WorkOrder.asset)).where(WorkOrder.work_order_id == uid)
    )
    return _wo_to_dict(wo) if wo else None
