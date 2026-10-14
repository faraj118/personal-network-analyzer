"""Planning/calendar routes (crm-direction). Follow-ups + .ics export."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.planning import planning_view, to_ics

router = APIRouter(tags=["planning"])


@router.get("/planning")
def planning() -> dict:
    """Contacts with a follow-up, split into overdue and upcoming."""
    return planning_view()


@router.get("/planning.ics")
def planning_ics() -> Response:
    """Download follow-ups as a calendar file (import into Google/Apple/Outlook)."""
    return Response(
        content=to_ics(),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=pnca-followups.ics"},
    )
