"""
Dashboard endpoints (Milestone 16).

Owner/dispatcher only — technicians don't see the dashboard per the
Technical Blueprint's role table, same all-or-nothing gate as payments.py.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.dashboard import DashboardMetrics, DashboardSummary
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_can_view_dashboard = require_role(UserRole.OWNER, UserRole.DISPATCHER)


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_view_dashboard),
):
    return await dashboard_service.get_summary(
        db, current_user.organization_id, date_from=date_from, date_to=date_to
    )


@router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_view_dashboard),
):
    return await dashboard_service.get_metrics(
        db, current_user.organization_id, date_from=date_from, date_to=date_to
    )
