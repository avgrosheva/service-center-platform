"""
Organization business logic (added post-Milestone-19, for the frontend's
Milestone F3 — App Shell & Navigation). Minimal by design: the only thing
the frontend actually needs is "what's the name of my own organization,"
for the user menu. Follows the same tenant-scoping convention as every
other service in this codebase: the organization_id always comes from
current_user (via the router), never from client input — there is no
way to request another organization's record through this module at all,
not even by 404 rejection, since no organization_id parameter exists on
its one function to begin with.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


async def get_own_organization(db: AsyncSession, organization_id: uuid.UUID) -> Organization:
    # get() rather than a defensive "not found" branch: organization_id
    # always comes from a valid JWT issued for a real, already-created
    # organization (Milestone 4's register flow creates both rows in one
    # transaction) — there is no code path that produces a token whose
    # organization_id doesn't exist, so an unhandled None here would mean
    # a genuine data-integrity bug elsewhere, not a normal 404 case.
    return await db.get_one(Organization, organization_id)
