"""Follow-up planning + calendar export (crm-direction: calendar/planning tools).

Surfaces contacts with a follow_up_date as overdue/upcoming, and exports them as a standard
.ics calendar (RFC 5545) you can import into any calendar app. 100% local, no cloud.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.db import connect, fetch_contacts


def _today() -> date:
    return datetime.now(UTC).date()


def _parse(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d.strip()[:10])
    except ValueError:
        return None


def planning_view(today: date | None = None) -> dict:
    """Partition contacts with a follow-up into overdue vs upcoming (sorted by date)."""
    today = today or _today()
    conn = connect()
    try:
        contacts = fetch_contacts(conn)
    finally:
        conn.close()
    items: list[dict] = []
    for c in contacts:
        d = _parse(c.get("follow_up_date"))
        if d is None:
            continue
        items.append(
            {
                "id": c["id"],
                "name": f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip(),
                "company": c.get("company"),
                "opportunity": c.get("opportunity"),
                "follow_up_date": d.isoformat(),
                "overdue": d < today,
                "days": (d - today).days,
            }
        )
    items.sort(key=lambda x: x["follow_up_date"])
    return {
        "overdue": [i for i in items if i["overdue"]],
        "upcoming": [i for i in items if not i["overdue"]],
        "count": len(items),
    }


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 §3.1 content-line folding: no line over 75 octets, split on a
    UTF-8 char boundary so Arabic/multi-byte summaries stay valid. Continuation
    lines begin with a single space (which counts toward the 75)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks: list[bytes] = []
    i, limit = 0, 75
    while i < len(raw):
        end = min(i + limit, len(raw))
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:  # don't split a code point
            end -= 1
        chunks.append(raw[i:end])
        i, limit = end, 74  # continuation lines carry a leading space
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def _next_day(iso: str) -> str:
    """DATE value for the day after an all-day event (DTEND is exclusive per RFC)."""
    d = date.fromisoformat(iso) + timedelta(days=1)
    return d.strftime("%Y%m%d")


def to_ics(items: list[dict] | None = None) -> str:
    """Render follow-ups as an RFC 5545 VCALENDAR (all-day VEVENTs)."""
    if items is None:
        v = planning_view()
        items = v["overdue"] + v["upcoming"]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PNCA//Follow-ups//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for it in items:
        summary = f"Follow up: {it['name']}"
        if it.get("company"):
            summary += f" ({it['company']})"
        start = it["follow_up_date"].replace("-", "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{it['id']}@pnca",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start}",
            f"DTEND;VALUE=DATE:{_next_day(it['follow_up_date'])}",
            f"SUMMARY:{_esc(summary)}",
        ]
        if it.get("opportunity"):
            lines.append(f"DESCRIPTION:{_esc('Opportunity: ' + it['opportunity'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"
