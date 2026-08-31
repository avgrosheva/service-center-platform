"""Pydantic v2 schemas for the dashboard endpoints (Milestone 16)."""

import uuid
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    active_jobs: int
    delayed_jobs: int
    completed_jobs: int
    unbilled_additional_work: int


class TechnicianRevenue(BaseModel):
    technician_id: uuid.UUID
    technician_name: str
    revenue: Decimal


class DashboardMetrics(BaseModel):
    avg_completion_time_hours: float | None
    revenue_per_technician: list[TechnicianRevenue]
    average_order_value: Decimal | None
    repeat_customer_rate: float
    warranty_case_count: int
