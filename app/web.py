"""Minimal local web UI (SPEC.md §2 frontend). Read-only view + CSV upload.

Bound to 127.0.0.1 via the server config; no auth (single-user, local, §15).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.db import (
    CLEAR,
    add_interaction,
    add_manual_contact,
    companies_summary,
    connect,
    data_health_summary,
    delete_view,
    edit_contact,
    fetch_contact,
    fetch_contacts,
    fetch_pending_enrichment,
    fetch_signals,
    fetch_views,
    insert_source_records,
    insights_summary,
    pipeline_board,
    rebuild_contacts,
    reconnect_candidates,
    save_view,
    soft_delete_contact,
)
from app.discovery.service import discovery_payload
from app.enrichment.base import EnrichmentClaim
from app.enrichment.profile import profile_for
from app.enrichment.service import decide, submit_claims
from app.llm.ask import parse_query
from app.llm.brief import prep_brief
from app.llm.outreach import draft_outreach
from app.pipeline.ingest_card import (
    _CARD_FIELDS,
    card_source_record_from_fields,
    read_card,
)
from app.pipeline.ingest_csv import ingest_linkedin_csv
from app.planning import planning_view
from app.tasks import (
    create_task,
    delete_task,
    list_tasks,
    open_task_summary,
    set_done,
)

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _safe_next(nxt: str | None, default: str = "/") -> str:
    """Only allow same-site relative redirects (leading single '/'), never an
    absolute or protocol-relative URL — closes an open-redirect even locally."""
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return default


def _flash(url: str, msg: str) -> RedirectResponse:
    """Redirect (303) with a one-shot confirmation banner carried in the query string.

    The banner is rendered by _nav.html on the destination page. Query-string only — no
    session/cookie needed for a single-user local app.
    """
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}flash={quote(msg)}", status_code=303)


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: str = "",
    industry: str = "",
    seniority: str = "",
    tag: str = "",
    pipeline_stage: str = "",
    min_score: int | None = None,
    missing: str = "",
) -> HTMLResponse:
    active = any([q, industry, seniority, tag, pipeline_stage, min_score, missing])
    conn = connect()
    try:
        all_contacts = fetch_contacts(conn)
        filtered = (
            fetch_contacts(
                conn,
                q=q or None,
                industry=industry or None,
                seniority=seniority or None,
                tag=tag or None,
                pipeline_stage=pipeline_stage or None,
                min_score=min_score,
                missing=missing or None,
            )
            if active
            else all_contacts
        )
        reconnect = reconnect_candidates(conn, days=90, limit=5)
        views = fetch_views(conn)
        tasks_today = open_task_summary(conn, limit=5)
    finally:
        conn.close()
    stats = {
        "total": len(all_contacts),
        "needs_review": sum(1 for c in all_contacts if c.get("needs_review")),
        "top_score": max((c.get("importance") or 0 for c in all_contacts), default=0),
        "c_level": sum(1 for c in all_contacts if c.get("seniority") == "C-Level"),
    }
    # "Today": who to act on — overdue follow-ups + top people to reach out to.
    plan = planning_view()
    with_opp = [c for c in all_contacts if c.get("opportunity")]
    top = (with_opp or all_contacts)[:5]
    today = {
        "overdue": plan["overdue"][:5],
        "top": top,
        "reconnect": reconnect,
        "tasks": tasks_today,
    }
    filters = {
        "q": q,
        "industry": industry,
        "seniority": seniority,
        "tag": tag,
        "pipeline_stage": pipeline_stage,
        "min_score": min_score if min_score is not None else "",
        "missing": missing,
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        {"contacts": filtered, "stats": stats, "today": today, "filters": filters, "views": views},
    )


@router.post("/ui/views/save")
def ui_save_view(
    name: Annotated[str, Form()],
    q: Annotated[str, Form()] = "",
    industry: Annotated[str, Form()] = "",
    seniority: Annotated[str, Form()] = "",
    tag: Annotated[str, Form()] = "",
    pipeline_stage: Annotated[str, Form()] = "",
    min_score: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Save the current filter set as a named view."""
    if name.strip():
        conn = connect()
        try:
            save_view(
                conn,
                name,
                {
                    "q": q,
                    "industry": industry,
                    "seniority": seniority,
                    "tag": tag,
                    "pipeline_stage": pipeline_stage,
                    "min_score": min_score,
                },
            )
        finally:
            conn.close()
        return _flash("/", f"Saved view “{name}”.")
    return RedirectResponse("/", status_code=303)


@router.post("/ui/views/{view_id}/delete")
def ui_delete_view(view_id: str) -> RedirectResponse:
    conn = connect()
    try:
        delete_view(conn, view_id)
    finally:
        conn.close()
    return RedirectResponse("/", status_code=303)


@router.get("/ask", response_class=HTMLResponse)
def ask(request: Request, question: str = "") -> HTMLResponse:
    """Ask-my-network: NL question -> LLM-parsed filters -> deterministic results."""
    results: list[dict] = []
    query: dict = {}
    if question.strip():
        query = parse_query(question)
        db_filters = {k: v for k, v in query.items() if not k.startswith("_")}
        conn = connect()
        try:
            results = fetch_contacts(conn, **db_filters)
        finally:
            conn.close()
    return templates.TemplateResponse(
        request, "ask.html", {"question": question, "query": query, "results": results}
    )


@router.get("/data-health", response_class=HTMLResponse)
def data_health(request: Request) -> HTMLResponse:
    """Data quality: missing fields, review queue, stale-important, backup."""
    conn = connect()
    try:
        data = data_health_summary(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "data_health.html", {"h": data})


@router.get("/insights", response_class=HTMLResponse)
def insights(request: Request) -> HTMLResponse:
    """Strategic overview: coverage vs targets, distributions, pipeline, data health."""
    conn = connect()
    try:
        data = insights_summary(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "insights.html", {"i": data})


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request) -> HTMLResponse:
    """Control center: config summary + actions (rebuild, company scan)."""
    from app.config import get_config
    from app.rules import get_rubric

    cfg = get_config()
    rubric = get_rubric()
    conn = connect()
    try:
        total = len(fetch_contacts(conn))
        scanned = conn.execute("SELECT COUNT(*) FROM company_intel").fetchone()[0]
    finally:
        conn.close()
    ctx = {
        "cfg": cfg,
        "rubric": rubric,
        "total": total,
        "companies_scanned": scanned,
    }
    return templates.TemplateResponse(request, "settings.html", ctx)


@router.post("/ui/settings/rebuild")
def ui_settings_rebuild() -> RedirectResponse:
    conn = connect()
    try:
        rebuild_contacts(conn)
    finally:
        conn.close()
    return RedirectResponse("/settings", status_code=303)


@router.post("/ui/settings/company-scan")
def ui_settings_company_scan() -> RedirectResponse:
    from app.enrichment.company_intel import scan_companies

    scan_companies(limit=25)  # small batch; rate-limited external lookups
    return RedirectResponse("/settings", status_code=303)


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline(request: Request) -> HTMLResponse:
    """Opportunity pipeline: contacts grouped by stage (Kanban)."""
    conn = connect()
    try:
        board = pipeline_board(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "pipeline.html", {"board": board})


@router.get("/companies", response_class=HTMLResponse)
def companies(request: Request) -> HTMLResponse:
    """Network grouped by organization: size, seniority, prominence."""
    conn = connect()
    try:
        rows = companies_summary(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "companies.html", {"companies": rows})


@router.get("/network", response_class=HTMLResponse)
def network(request: Request) -> HTMLResponse:
    """Type-B discovery page: bridges, hubs, communities, gaps (SPEC.md §8)."""
    d = discovery_payload(top_n=10)
    return templates.TemplateResponse(request, "network.html", {"d": d})


@router.get("/calendar", response_class=HTMLResponse)
def calendar(request: Request) -> HTMLResponse:
    """Follow-up planning page: overdue + upcoming, with a calendar (.ics) export.

    Human page lives at /calendar so it doesn't shadow the JSON API at GET /planning.
    """
    return templates.TemplateResponse(request, "planning.html", {"p": planning_view()})


@router.get("/review", response_class=HTMLResponse)
def review(request: Request) -> HTMLResponse:
    """Review queue: pending enrichment claims (accept/reject) + opportunity signals (§18)."""
    conn = connect()
    try:
        pending = fetch_pending_enrichment(conn)
        signals = fetch_signals(conn)
        names = {
            c["id"]: f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip()
            for c in fetch_contacts(conn)
        }
    finally:
        conn.close()
    for p in pending:
        p["contact_name"] = names.get(p["contact_id"], "(unknown)")
    for s in signals:
        s["contact_name"] = names.get(s["contact_id"], "(unknown)")
    return templates.TemplateResponse(
        request, "review.html", {"pending": pending, "signals": signals}
    )


@router.get("/contact/{contact_id}", response_class=HTMLResponse)
def contact_detail(request: Request, contact_id: str) -> HTMLResponse:
    """Per-contact profile: base fields + accepted sourced claims + signals (SPEC.md §18)."""
    d = profile_for(contact_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    conn = connect()
    try:
        contact_tasks = list_tasks(conn, contact_id=contact_id)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "contact.html", {"d": d, "tasks": contact_tasks})


@router.post("/ui/contact/{contact_id}/claim")
def ui_add_claim(
    contact_id: str,
    field: Annotated[str, Form()],
    value: Annotated[str, Form()],
    source_url: Annotated[str, Form()],
) -> RedirectResponse:
    """Add a sourced claim from the detail page -> pending review (provenance required, §18)."""
    if value.strip() and source_url.strip():
        submit_claims(
            [
                EnrichmentClaim(
                    contact_id=contact_id,
                    field=field,
                    value=value,
                    method="web_public",
                    source_url=source_url,
                    confidence=0.8,
                )
            ]
        )
    return RedirectResponse(f"/contact/{contact_id}", status_code=303)


@router.post("/ui/review/{item_id}/{action}")
def ui_review_decide(item_id: str, action: str) -> RedirectResponse:
    """Accept/reject a claim from the review page (plain-form friendly)."""
    if action in ("accept", "reject"):
        decide(item_id, accept=action == "accept")
        return _flash("/review", f"Claim {action}ed.")
    return RedirectResponse("/review", status_code=303)


@router.post("/ui/contact/{contact_id}/edit")
def ui_edit_contact(
    contact_id: str,
    first_name: Annotated[str, Form()] = "",
    last_name: Annotated[str, Form()] = "",
    job_title: Annotated[str, Form()] = "",
    company: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    seniority: Annotated[str, Form()] = "",
    opportunity: Annotated[str, Form()] = "",
    website: Annotated[str, Form()] = "",
    follow_up_date: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    pipeline_stage: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Save CRM edits from the contact page (blank fields are left unchanged)."""
    edits = {
        k: v
        for k, v in {
            "first_name": first_name,
            "last_name": last_name,
            "job_title": job_title,
            "company": company,
            "email": email,
            "phone": phone,
            "location": location,
            "seniority": seniority,
            "opportunity": opportunity,
            "website": website,
            "follow_up_date": follow_up_date,
            "notes": notes,
            "tags": tags,
            "pipeline_stage": pipeline_stage,
        }.items()
        if v.strip()
    }
    conn = connect()
    try:
        edit_contact(conn, contact_id, edits)
    finally:
        conn.close()
    return _flash(f"/contact/{contact_id}", "Saved.")


@router.post("/ui/contact/{contact_id}/draft", response_class=HTMLResponse)
def ui_draft(
    request: Request, contact_id: str, intent: Annotated[str, Form()] = "reconnect"
) -> HTMLResponse:
    """Generate an outreach draft and re-render the contact page with it shown."""
    d = profile_for(contact_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    draft = draft_outreach(d, intent)
    return templates.TemplateResponse(
        request, "contact.html", {"d": d, "draft": draft, "draft_intent": intent}
    )


@router.post("/ui/contact/{contact_id}/brief", response_class=HTMLResponse)
def ui_brief(request: Request, contact_id: str) -> HTMLResponse:
    """Generate a prep brief and re-render the contact page with it shown."""
    d = profile_for(contact_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    brief = prep_brief(d)
    return templates.TemplateResponse(request, "contact.html", {"d": d, "brief": brief})


@router.post("/ui/contact/{contact_id}/stage")
def ui_set_stage(contact_id: str, stage: Annotated[str, Form()] = "") -> RedirectResponse:
    """Move a contact between pipeline stages from the board ('__clear__' removes it)."""
    conn = connect()
    try:
        edit_contact(conn, contact_id, {"pipeline_stage": stage})
    finally:
        conn.close()
    return RedirectResponse("/pipeline", status_code=303)


@router.post("/ui/contact/{contact_id}/interaction")
def ui_add_interaction(
    contact_id: str,
    occurred_on: Annotated[str, Form()] = "",
    kind: Annotated[str, Form()] = "note",
    note: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Log a touchpoint from the contact page."""
    conn = connect()
    try:
        add_interaction(conn, contact_id, occurred_on, kind, note)
    finally:
        conn.close()
    return _flash(f"/contact/{contact_id}", "Touchpoint logged.")


@router.post("/ui/contact/{contact_id}/delete")
def ui_delete_contact(contact_id: str) -> RedirectResponse:
    conn = connect()
    try:
        soft_delete_contact(conn, contact_id)
    finally:
        conn.close()
    return RedirectResponse("/", status_code=303)


@router.post("/ui/contacts/bulk")
def ui_bulk(
    ids: Annotated[list[str] | None, Form()] = None,
    action: Annotated[str, Form()] = "",
    tag: Annotated[str, Form()] = "",
    stage: Annotated[str, Form()] = "",
    follow_up_date: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Apply one action to several selected contacts at once (from the list).

    The action is carried by the clicked button's value; edits go through
    edit_contact so they persist across rebuilds and rescore like single edits.
    """
    ids = [i for i in (ids or []) if i]
    if not ids:
        return _flash("/", "Select some contacts first.")
    conn = connect()
    n = 0
    try:
        for cid in ids:
            if action == "add_tag" and tag.strip():
                c = fetch_contact(conn, cid)
                if c is None:
                    continue
                existing = [t.strip() for t in (c.get("tags") or "").split(",") if t.strip()]
                if tag.strip() not in existing:
                    existing.append(tag.strip())
                edit_contact(conn, cid, {"tags": ", ".join(existing)})
            elif action == "set_stage" and stage.strip():
                edit_contact(conn, cid, {"pipeline_stage": stage})
            elif action == "set_follow_up" and follow_up_date.strip():
                edit_contact(conn, cid, {"follow_up_date": follow_up_date})
            elif action == "clear_follow_up":
                edit_contact(conn, cid, {"follow_up_date": CLEAR})
            else:
                continue
            n += 1
    finally:
        conn.close()
    labels = {
        "add_tag": f"Tagged {n}",
        "set_stage": f"Moved {n} to {stage}",
        "set_follow_up": f"Set follow-up on {n}",
        "clear_follow_up": f"Cleared follow-up on {n}",
    }
    return _flash("/", labels.get(action, f"Updated {n}") + " contact(s).")


@router.post("/ui/contact/add")
def ui_add_contact(
    first_name: Annotated[str, Form()] = "",
    last_name: Annotated[str, Form()] = "",
    company: Annotated[str, Form()] = "",
    job_title: Annotated[str, Form()] = "",
    seniority: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    website: Annotated[str, Form()] = "",
) -> RedirectResponse:
    fields = {
        "first_name": first_name,
        "last_name": last_name,
        "company": company,
        "job_title": job_title,
        "seniority": seniority,
        "email": email,
        "website": website,
    }
    conn = connect()
    try:
        add_manual_contact(conn, {k: v for k, v in fields.items() if v.strip()})
    finally:
        conn.close()
    name = f"{first_name} {last_name}".strip() or "contact"
    return _flash("/", f"Added {name}.")


@router.post("/ui/upload-card")
async def ui_upload_card(
    request: Request, files: Annotated[list[UploadFile], File(...)]
) -> Response:
    """OCR business-card images, then show an editable review screen before saving (§6).

    Nothing is written to the DB here — the user confirms/corrects the extracted fields
    on card_review.html, which posts to /ui/cards/confirm.
    """
    cards = []
    for f in files:
        data = await f.read()
        if not data:
            continue
        card = read_card(data, origin_file=f.filename)
        if card is None:
            continue
        mime = f.content_type or "image/jpeg"
        card["image_data_uri"] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        cards.append(card)
    if not cards:
        return _flash("/", "Couldn't read any text from those images — try a clearer, flat photo.")
    return templates.TemplateResponse(request, "card_review.html", {"cards": cards})


@router.post("/ui/cards/confirm")
async def ui_cards_confirm(request: Request) -> RedirectResponse:
    """Save reviewed cards: build source_records from the confirmed fields, then rebuild."""
    form = await request.form()
    idxs = sorted({k.split("-")[1] for k in form if k.startswith("card-")}, key=int)
    records = []
    for i in idxs:
        p = f"card-{i}-"
        raw_text = str(form.get(p + "raw_text") or "")
        try:
            conf = float(form.get(p + "confidence") or 0)
        except ValueError:
            conf = 0.0
        origin = str(form.get(p + "origin_file") or "") or None
        fields = {f: str(form.get(p + f) or "").strip() for f in _CARD_FIELDS}
        fields = {k: v for k, v in fields.items() if v}
        if not fields:
            continue
        records.append(card_source_record_from_fields(fields, raw_text, conf, origin))
    if not records:
        return _flash("/", "Nothing to add — the cards had no fields filled in.")
    conn = connect()
    try:
        insert_source_records(conn, records)
        rebuild_contacts(conn)
    finally:
        conn.close()
    return _flash("/", f"Added {len(records)} contact(s) from cards.")


@router.post("/ui/upload")
async def ui_upload(files: Annotated[list[UploadFile], File(...)]) -> RedirectResponse:
    """Accept LinkedIn CSV(s) from the browser form, ingest + rebuild, back to home."""
    added = 0
    conn = connect()
    try:
        for f in files:
            if (f.filename or "").lower().endswith(".csv"):
                records = ingest_linkedin_csv(await f.read(), origin_file=f.filename)
                insert_source_records(conn, records)
                added += len(records)
        rebuild_contacts(conn)
    finally:
        conn.close()
    return _flash("/", f"Imported {added} record(s) from CSV.")


@router.post("/ui/contact/{contact_id}/logtouch")
def ui_log_touch(contact_id: str, next: Annotated[str, Form()] = "/") -> RedirectResponse:
    """One-click 'I reached out': log a touchpoint today and clear the follow-up flag."""
    conn = connect()
    try:
        add_interaction(conn, contact_id, "", "note", "Logged from Today")
        edit_contact(conn, contact_id, {"follow_up_date": CLEAR})
    finally:
        conn.close()
    return _flash(_safe_next(next), "Logged a touch and cleared the follow-up.")


@router.post("/ui/contact/{contact_id}/snooze")
def ui_snooze(
    contact_id: str,
    days: Annotated[int, Form()] = 7,
    next: Annotated[str, Form()] = "/",
) -> RedirectResponse:
    """Push a follow-up out by N days from the Today panel or Planning page."""
    new_date = (datetime.now(UTC).date() + timedelta(days=days)).isoformat()
    conn = connect()
    try:
        edit_contact(conn, contact_id, {"follow_up_date": new_date})
    finally:
        conn.close()
    return _flash(_safe_next(next), f"Snoozed {days} days — back on {new_date}.")


@router.post("/ui/contact/{contact_id}/reschedule")
def ui_reschedule(
    contact_id: str,
    follow_up_date: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/calendar",
) -> RedirectResponse:
    """Set a follow-up to a specific date (from the Planning page)."""
    dest = _safe_next(next, "/calendar")
    if not follow_up_date.strip():
        return _flash(dest, "Pick a date to reschedule to.")
    conn = connect()
    try:
        edit_contact(conn, contact_id, {"follow_up_date": follow_up_date.strip()})
    finally:
        conn.close()
    return _flash(dest, f"Rescheduled to {follow_up_date.strip()}.")


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request) -> HTMLResponse:
    """Tasks / reminders: open list first, done list below."""
    conn = connect()
    try:
        open_tasks = list_tasks(conn, done=False)
        done_tasks = list_tasks(conn, done=True)
    finally:
        conn.close()
    today = datetime.now(UTC).date().isoformat()
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {"open_tasks": open_tasks, "done_tasks": done_tasks, "today": today},
    )


@router.post("/ui/tasks/add")
def ui_task_add(
    title: Annotated[str, Form()] = "",
    due_date: Annotated[str, Form()] = "",
    contact_id: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/tasks",
) -> RedirectResponse:
    """Create a task (optionally linked to a contact)."""
    dest = _safe_next(next, "/tasks")
    conn = connect()
    try:
        created = create_task(conn, title, due_date=due_date, contact_id=contact_id, notes=notes)
    finally:
        conn.close()
    return _flash(dest, "Task added." if created else "A task needs a title.")


@router.post("/ui/tasks/{task_id}/done")
def ui_task_done(task_id: str, next: Annotated[str, Form()] = "/tasks") -> RedirectResponse:
    conn = connect()
    try:
        set_done(conn, task_id, True)
    finally:
        conn.close()
    return _flash(_safe_next(next, "/tasks"), "Task completed.")


@router.post("/ui/tasks/{task_id}/reopen")
def ui_task_reopen(task_id: str, next: Annotated[str, Form()] = "/tasks") -> RedirectResponse:
    conn = connect()
    try:
        set_done(conn, task_id, False)
    finally:
        conn.close()
    return _flash(_safe_next(next, "/tasks"), "Task reopened.")


@router.post("/ui/tasks/{task_id}/delete")
def ui_task_delete(task_id: str, next: Annotated[str, Form()] = "/tasks") -> RedirectResponse:
    conn = connect()
    try:
        delete_task(conn, task_id)
    finally:
        conn.close()
    return _flash(_safe_next(next, "/tasks"), "Task deleted.")
