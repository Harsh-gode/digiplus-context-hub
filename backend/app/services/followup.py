"""Follow-up Autopilot: predict which open items will slip, and draft the follow-up message.

1. `risk_for()` scores every open item 0-100 with human-readable reasons. It is a transparent,
   rule-based model on purpose: every point can be explained to the person being chased.
2. `draft_nudge()` asks the AI to write one personalised message per owner covering their
   riskiest items (rule-based template if AI is unavailable).
3. Sending is recorded as a `nudged` event in each item's history, so the follow-up trail is auditable.
"""
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..logging_setup import get_logger
from ..models import CLOSED_ITEM_STATUSES, ActionItem, ItemHistory, Meeting, Participant
from .ai_client import call_json

log = get_logger("followup")

HIGH, MEDIUM = 60, 35


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def risk_for(item: ActionItem, owner_open: int, last_nudged: datetime | None, today: date | None = None) -> dict:
    """Return {score, level, reasons} for one open item. Each rule adds points and says why."""
    today = today or date.today()
    score, reasons = 0, []

    def add(points: int, why: str):
        nonlocal score
        score += points
        reasons.append(why)

    if not item.owner:
        add(25, "no owner")
    if item.due_date is None:
        add(10, "no due date")
    elif item.due_date < today:
        days = (today - item.due_date).days
        add(35 + min(days * 3, 15), f"overdue {days} day{'s' if days != 1 else ''}")
    elif (item.due_date - today).days <= 2 and item.status == "open":
        add(15, f"due in {(item.due_date - today).days} day(s), not started")
    if item.times_carried:
        add(min(item.times_carried * 12, 30), f"carried forward {item.times_carried}×")
    if item.status == "blocked":
        add(20, "blocked")
    if item.priority == "high":
        add(10, "high priority")
    if item.owner and owner_open >= 4:
        add(10, f"owner has {owner_open} open items")
    age = (today - _aware(item.created_at).date()).days
    if age > 14:
        add(5, f"open {age} days")
    if item.status == "in_progress":
        score -= 10
        reasons.append("in progress (−10)")
    if last_nudged and (datetime.now(timezone.utc) - _aware(last_nudged)).days < 2:
        score -= 15
        reasons.append("nudged recently (−15)")

    score = max(0, min(100, score))
    level = "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"
    return {"score": score, "level": level, "reasons": reasons}


def _last_nudges(db: Session, item_ids: list[int]) -> dict[int, datetime]:
    if not item_ids:
        return {}
    rows = db.execute(
        select(ItemHistory.item_id, ItemHistory.created_at)
        .where(ItemHistory.item_id.in_(item_ids), ItemHistory.event == "nudged")
        .order_by(ItemHistory.created_at)
    ).all()
    return {item_id: created for item_id, created in rows}  # later rows overwrite → latest


def owner_email(db: Session, name: str) -> str:
    return db.scalar(
        select(Participant.email).where(Participant.name == name, Participant.email != "").order_by(Participant.id.desc()).limit(1)
    ) or ""


def build_board(db: Session) -> dict:
    """All open items grouped by owner, each scored, owners sorted by their highest risk."""
    items = db.scalars(select(ActionItem).where(ActionItem.status.not_in(CLOSED_ITEM_STATUSES))).all()
    load = defaultdict(int)
    for i in items:
        load[i.owner] += 1
    nudges = _last_nudges(db, [i.id for i in items])
    titles = dict(db.execute(select(Meeting.id, Meeting.title)).all())

    groups = defaultdict(list)
    for i in items:
        r = risk_for(i, load[i.owner], nudges.get(i.id))
        groups[i.owner or ""].append({
            "id": i.id, "title": i.title, "owner": i.owner, "status": i.status, "priority": i.priority,
            "due_date": i.due_date.isoformat() if i.due_date else None, "times_carried": i.times_carried,
            "meeting_id": i.current_meeting_id, "meeting_title": titles.get(i.current_meeting_id, ""),
            "last_nudged": _aware(nudges[i.id]).isoformat() if i.id in nudges else None, **r,
        })

    owners = []
    for name, its in groups.items():
        its.sort(key=lambda x: -x["score"])
        owners.append({
            "owner": name, "email": owner_email(db, name) if name else "",
            "max_score": its[0]["score"], "high": sum(x["level"] == "high" for x in its),
            "medium": sum(x["level"] == "medium" for x in its), "items": its,
        })
    owners.sort(key=lambda o: (-o["max_score"], o["owner"] == ""))
    all_items = [x for o in owners for x in o["items"]]
    return {
        "summary": {
            "open": len(all_items),
            "high": sum(x["level"] == "high" for x in all_items),
            "medium": sum(x["level"] == "medium" for x in all_items),
            "owners_to_nudge": sum(1 for o in owners if o["owner"] and o["high"]),
        },
        "owners": owners,
    }


NUDGE_SYSTEM = """You write short follow-up messages from a delivery manager to a colleague about their open action items.
Goal: get each item moving or get an honest new date — without blame.
Rules:
- Address the person by first name. One message covering all listed items, most urgent first.
- For each item: what it is, why it matters now (use the given risk reasons: overdue, carried forward, blocked…), and ONE concrete ask
  (e.g. "can you confirm a new date?", "what's blocking you — can I help unblock?").
- tone "friendly": warm, collaborative. tone "firm": polite but direct, clear deadline for a reply.
- channel "slack": under 90 words, short lines, no subject. channel "email": a subject line + under 150 words.
- Use only facts given. No invented dates, people or numbers.
Return JSON: {"subject": str (empty for slack), "message": str}"""


def draft_nudge(owner: str, items: list[dict], tone: str, channel: str, sender: str = "") -> dict:
    lines = "\n".join(
        f"- {i['title']} | due {i['due_date'] or 'none'} | status {i['status']} | from '{i['meeting_title']}' | risk {i['score']}: {', '.join(i['reasons'])}"
        for i in items
    )
    user = f"To: {owner}\nFrom: {sender or 'the delivery manager'}\nTone: {tone}\nChannel: {channel}\nToday: {date.today().isoformat()}\nItems:\n{lines}"

    def _validate(d):
        if not isinstance(d.get("message"), str) or len(d["message"].strip()) < 20:
            raise ValueError("message missing")

    result = call_json("draft_nudge", NUDGE_SYSTEM, user, validate=_validate)
    if result.data:
        return {"subject": str(result.data.get("subject") or ""), "message": result.data["message"].strip(),
                "ai_status": "ok", "ai_message": ""}

    first = owner.split()[0] if owner else "there"
    bullets = "\n".join(f"• {i['title']} — {', '.join(r for r in i['reasons'] if '−' not in r) or 'open'}" for i in items)
    ask = "Could you reply by end of day with a status or a new date for each?" if tone == "firm" else \
        "Could you share a quick status or a realistic new date when you get a moment? Happy to help unblock anything."
    body = f"Hi {first}, quick follow-up on a few open items:\n\n{bullets}\n\n{ask}"
    return {"subject": f"Follow-up: {len(items)} open item{'s' if len(items) != 1 else ''}" if channel == "email" else "",
            "message": body, "ai_status": result.status, "ai_message": result.message}
