"""
Organization endpoints — added post-Milestone-19 for the frontend's
Milestone F3, which needs the caller's own organization name for its
user-menu display (name + org + logout) and found no existing endpoint
that returns it (`OrganizationRead` was declared in Milestone 3 but never
wired to a router). `/organizations/me` is the minimal fix: any
authenticated user (owner/dispatcher/technician — no role restriction,
since every role's nav shell shows the same user menu) can read their own
organization's name, and only their own — there's no way to request
another organization's record through this route at all.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.organization import OrganizationRead
from app.services import organization_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me", response_model=OrganizationRead)
async def get_my_organization(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await organization_service.get_own_organization(db, current_user.organization_id)
