"""Domain operations: lifecycle rules, carry-forward, item history, knowledge/conflict orchestration.

Routers stay thin and call into here, so the rules live in one place.
"""
import contextvars
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..logging_setup import get_logger
from ..models import (
    CLOSED_ITEM_STATUSES, ActionItem, Decision, DecisionConflict, ItemHistory, KnowledgeDoc, KnowledgeLink,
    Meeting, Participant,
)
from ..schemas import ConflictOut, ItemDetail, ItemOut, LinkOut, MeetingDetail, MeetingSummaryOut
from . import intelligence
from .retrieval import Candidate, bm25_rank

log = get_logger("workflow")

ALLOWED_TRANSITIONS = {
    "scheduled": {"in_progress", "completed", "cancelled"},
    "in_progress": {"completed", "cancelled", "scheduled"},
    "completed": {"in_progress"},  # reopen
    "cancelled": {"scheduled"},
}


# ---------------------------------------------------------------- helpers
def get_meeting_or_404(db: Session, meeting_id: int) -> Meeting:
    m = db.get(Meeting, meeting_id, options=[selectinload(Meeting.participants), selectinload(Meeting.notes), selectinload(Meeting.decisions)])
    if not m:
        raise HTTPException(404, f"Meeting {meeting_id} not found")
    return m


def get_item_or_404(db: Session, item_id: int) -> ActionItem:
    item = db.get(ActionItem, item_id)
    if not item:
        raise HTTPException(404, f"Action item {item_id} not found")
    return item


def is_overdue(item: ActionItem) -> bool:
    return bool(item.due_date and item.status not in CLOSED_ITEM_STATUSES and item.due_date < date.today())


def item_out(item: ActionItem) -> ItemOut:
    out = ItemOut.model_validate(item)
    out.is_overdue = is_overdue(item)
    return out


def item_detail(db: Session, item: ActionItem) -> ItemDetail:
    d = ItemDetail.model_validate(item)
    d.is_overdue = is_overdue(item)
    titles = dict(db.execute(select(Meeting.id, Meeting.title).where(Meeting.id.in_([item.origin_meeting_id, item.current_meeting_id]))).all())
    d.origin_meeting_title = titles.get(item.origin_meeting_id, "")
    d.current_meeting_title = titles.get(item.current_meeting_id, "")
    return d


def add_history(db: Session, item: ActionItem, event: str, from_value="", to_value="", note="", meeting_id=None):
    db.add(ItemHistory(item_id=item.id, event=event, from_value=str(from_value or ""), to_value=str(to_value or ""),
                       note=note or "", meeting_id=meeting_id or item.current_meeting_id))


def meeting_summary_rows(db: Session, meetings: list[Meeting]) -> list[MeetingSummaryOut]:
    ids = [m.id for m in meetings]
    if not ids:
        return []
    pc = dict(db.execute(select(Participant.meeting_id, func.count()).where(Participant.meeting_id.in_(ids)).group_by(Participant.meeting_id)).all())
    oc = dict(db.execute(
        select(ActionItem.current_meeting_id, func.count())
        .where(ActionItem.current_meeting_id.in_(ids), ActionItem.status.not_in(CLOSED_ITEM_STATUSES))
        .group_by(ActionItem.current_meeting_id)
    ).all())
    cc = dict(db.execute(
        select(DecisionConflict.meeting_id, func.count())
        .where(DecisionConflict.meeting_id.in_(ids), DecisionConflict.status == "open").group_by(DecisionConflict.meeting_id)
    ).all())
    rows = []
    for m in meetings:
        r = MeetingSummaryOut.model_validate(m)
        r.participant_count, r.open_item_count, r.open_conflicts = pc.get(m.id, 0), oc.get(m.id, 0), cc.get(m.id, 0)
        rows.append(r)
    return rows


def meeting_detail(db: Session, m: Meeting) -> MeetingDetail:
    d = MeetingDetail.model_validate(m)
    if m.previous_id:
        prev = db.get(Meeting, m.previous_id)
        d.previous_title = prev.title if prev else ""
    d.next_id = db.scalar(select(Meeting.id).where(Meeting.previous_id == m.id).order_by(Meeting.scheduled_at).limit(1))
    items = db.scalars(select(ActionItem).where(ActionItem.current_meeting_id == m.id).order_by(ActionItem.status, ActionItem.due_date)).all()
    d.items = [item_out(i) for i in items]
    d.links = links_for_meeting(db, m.id)
    d.conflicts = conflicts_for(db, meeting_id=m.id)
    return d


# ---------------------------------------------------------------- lifecycle
def change_status(db: Session, m: Meeting, new_status: str) -> Meeting:
    if new_status == m.status:
        return m
    if new_status not in ALLOWED_TRANSITIONS.get(m.status, set()):
        raise HTTPException(409, f"Cannot move a {m.status.replace('_', ' ')} {m.kind} to {new_status.replace('_', ' ')}")
    old = m.status
    m.status = new_status
    db.commit()
    log.info("meeting.status_changed", meeting_id=m.id, from_status=old, to_status=new_status)
    return m


def carry_forward(db: Session, from_meeting: Meeting, to_meeting: Meeting) -> list[ActionItem]:
    """Move every still-open item of `from_meeting` onto `to_meeting`, keeping its history."""
    if from_meeting.id == to_meeting.id:
        raise HTTPException(400, "Cannot carry items forward to the same meeting")
    items = db.scalars(
        select(ActionItem).where(ActionItem.current_meeting_id == from_meeting.id, ActionItem.status.not_in(CLOSED_ITEM_STATUSES))
    ).all()
    for item in items:
        item.current_meeting_id = to_meeting.id
        item.times_carried += 1
        add_history(db, item, "carried_forward", from_meeting.title, to_meeting.title,
                    note=f"Carried forward (x{item.times_carried})", meeting_id=to_meeting.id)
    db.commit()
    for item in items:
        log.info("item.carried_forward", item_id=item.id, from_meeting_id=from_meeting.id, to_meeting_id=to_meeting.id,
                 times_carried=item.times_carried)
    return items


def create_item(db: Session, meeting: Meeting, *, title, owner="", due_date=None, priority="medium", description="", source="manual") -> ActionItem:
    item = ActionItem(title=title.strip(), owner=(owner or "").strip(), due_date=due_date, priority=priority, description=description,
                      source=source, origin_meeting_id=meeting.id, current_meeting_id=meeting.id)
    db.add(item)
    db.flush()
    add_history(db, item, "created", to_value=item.title, note=f"Source: {source}", meeting_id=meeting.id)
    log.info("item.created", item_id=item.id, meeting_id=meeting.id, source=source, has_owner=bool(item.owner), has_due=bool(due_date))
    return item


def update_item(db: Session, item: ActionItem, changes: dict, note: str = "") -> ActionItem:
    if item.status in CLOSED_ITEM_STATUSES and changes:
        if "status" not in changes:
            raise HTTPException(409, "Item is closed. Reopen it first by setting status to open.")
    events = []
    for field, value in changes.items():
        old = getattr(item, field)
        if old == value:
            continue
        setattr(item, field, value)
        if field == "owner":
            add_history(db, item, "reassigned", old, value, note)
            events.append(("item.reassigned", {"from_owner": old or None, "to_owner": value or None}))
        elif field == "status":
            reopened = old in CLOSED_ITEM_STATUSES
            if reopened:
                item.closed_at = None
            add_history(db, item, "reopened" if reopened else "status_changed", old, value, note)
            events.append(("item.reopened" if reopened else "item.status_changed", {"from_status": old, "to_status": value}))
        elif field == "due_date":
            add_history(db, item, "due_changed", old, value, note)
            events.append(("item.due_changed", {}))
        else:
            add_history(db, item, f"{field}_changed", old, value, note)
    db.commit()
    for name, extra in events:
        log.info(name, item_id=item.id, **extra)
    return item


def close_item(db: Session, item: ActionItem, status: str, outcome: str) -> ActionItem:
    if item.status in CLOSED_ITEM_STATUSES:
        raise HTTPException(409, "Item is already closed")
    old = item.status
    item.status, item.outcome, item.closed_at = status, outcome.strip(), datetime.now(timezone.utc)
    add_history(db, item, "closed", old, status, note=outcome)
    db.commit()
    log.info("item.closed", item_id=item.id, final_status=status, times_carried=item.times_carried,
             age_days=(date.today() - item.created_at.date()).days)
    return item


# ---------------------------------------------------------------- knowledge
def build_corpus(db: Session, exclude_meeting_id: int | None = None, include_items: bool = False) -> list[Candidate]:
    cands = [Candidate("doc", d.id, d.title, f"{d.content}\nTags: {d.tags}", {"doc_type": d.doc_type})
             for d in db.scalars(select(KnowledgeDoc)).all()]
    meetings = db.scalars(select(Meeting).options(selectinload(Meeting.decisions))).all()
    for m in meetings:
        if m.id == exclude_meeting_id:
            continue
        text = f"{m.summary}\nAgenda: {m.agenda}\nDecisions: " + " | ".join(d.text for d in m.decisions)
        if text.strip():
            cands.append(Candidate("meeting", m.id, f"{m.title} ({m.scheduled_at.date()})", text, {"date": str(m.scheduled_at.date())}))
    if include_items:
        for i in db.scalars(select(ActionItem)).all():
            cands.append(Candidate("item", i.id, i.title, f"{i.title}. Owner {i.owner}. Status {i.status}. Due {i.due_date}. Outcome: {i.outcome}", {}))
    return cands


def meeting_text(m: Meeting) -> str:
    return "\n".join([m.title, m.agenda, m.summary, *(d.text for d in m.decisions), *(n.content[:2000] for n in m.notes)])


def links_for_meeting(db: Session, meeting_id: int) -> list[LinkOut]:
    rows = db.scalars(select(KnowledgeLink).where(KnowledgeLink.meeting_id == meeting_id).order_by(KnowledgeLink.score.desc())).all()
    doc_titles = dict(db.execute(select(KnowledgeDoc.id, KnowledgeDoc.title)).all())
    meet_titles = dict(db.execute(select(Meeting.id, Meeting.title)).all())
    return [
        LinkOut(id=r.id, item_id=r.item_id, doc_id=r.doc_id, linked_meeting_id=r.linked_meeting_id,
                title=doc_titles.get(r.doc_id, "") if r.doc_id else meet_titles.get(r.linked_meeting_id, ""),
                reason=r.reason, score=r.score, source=r.source)
        for r in rows
    ]


def refresh_links(db: Session, m: Meeting) -> dict:
    items = db.scalars(select(ActionItem).where(ActionItem.current_meeting_id == m.id)).all()
    query = meeting_text(m) + "\n" + "\n".join(i.title for i in items)
    candidates = bm25_rank(query, build_corpus(db, exclude_meeting_id=m.id), top_k=8)
    result = intelligence.link_knowledge(query, [{"id": i.id, "title": i.title, "owner": i.owner} for i in items], candidates)

    db.query(KnowledgeLink).filter(KnowledgeLink.meeting_id == m.id).delete()
    for l in result["links"]:
        c = l["candidate"]
        db.add(KnowledgeLink(meeting_id=m.id, item_id=l["item_id"], doc_id=c.id if c.kind == "doc" else None,
                             linked_meeting_id=c.id if c.kind == "meeting" else None,
                             reason=l["reason"], score=l["score"], source=l["source"]))
    db.commit()
    log.info("knowledge.linked", meeting_id=m.id, candidates=len(candidates), links=len(result["links"]), ai_status=result["ai_status"])
    return {"links": links_for_meeting(db, m.id), "ai_status": result["ai_status"], "ai_message": result["ai_message"]}


# ---------------------------------------------------------------- conflicts (special feature)
def conflicts_for(db: Session, meeting_id: int | None = None, status: str | None = None) -> list[ConflictOut]:
    q = select(DecisionConflict).order_by(DecisionConflict.created_at.desc())
    if meeting_id:
        q = q.where(DecisionConflict.meeting_id == meeting_id)
    if status:
        q = q.where(DecisionConflict.status == status)
    rows = db.scalars(q).all()
    out = []
    for r in rows:
        dec = db.get(Decision, r.decision_id)
        other_text, other_title, other_meeting = "", "", None
        if r.conflicting_decision_id:
            od = db.get(Decision, r.conflicting_decision_id)
            if od:
                om = db.get(Meeting, od.meeting_id)
                other_text, other_title, other_meeting = od.text, f"{om.title} ({om.scheduled_at.date()})", om.id
        elif r.conflicting_doc_id:
            doc = db.get(KnowledgeDoc, r.conflicting_doc_id)
            if doc:
                other_text, other_title = doc.content[:400], doc.title
        out.append(ConflictOut(
            id=r.id, decision_id=r.decision_id, decision_text=dec.text if dec else "", meeting_id=r.meeting_id,
            conflicting_decision_id=r.conflicting_decision_id, conflicting_text=other_text, conflicting_source_title=other_title,
            conflicting_meeting_id=other_meeting, conflicting_doc_id=r.conflicting_doc_id, severity=r.severity,
            explanation=r.explanation, suggestion=r.suggestion, status=r.status, resolution_note=r.resolution_note,
            created_at=r.created_at,
        ))
    return out


def _conflict_candidates(db: Session, decision: Decision) -> list[Candidate]:
    cands = [Candidate("doc", d.id, d.title, d.content, {}) for d in db.scalars(select(KnowledgeDoc)).all()]
    rows = db.execute(
        select(Decision, Meeting.title, Meeting.scheduled_at).join(Meeting, Meeting.id == Decision.meeting_id)
        .where(Decision.meeting_id != decision.meeting_id)
    ).all()
    for d, title, when in rows:
        cands.append(Candidate("decision", d.id, d.text[:80], f"{d.text} {d.rationale}", {"meeting_title": title, "date": str(when.date())}))
    return bm25_rank(decision.text + " " + decision.rationale, cands, top_k=6)


def check_conflicts(db: Session, decisions: list[Decision], meeting: Meeting) -> dict:
    """Run conflict detection for several decisions in parallel (one AI call each)."""
    if not decisions:
        return {"found": 0, "ai_status": "ok", "ai_message": ""}
    jobs = [(d, _conflict_candidates(db, d)) for d in decisions]

    def run(job):
        d, cands = job
        return d, intelligence.detect_conflicts(d.text, meeting.title, cands)

    with ThreadPoolExecutor(max_workers=4) as pool:
        # copy_context so the request ID follows the work into worker threads
        futures = [pool.submit(contextvars.copy_context().run, run, j) for j in jobs]
        results = [f.result() for f in futures]

    found, statuses, message = 0, set(), ""
    for d, res in results:
        statuses.add(res["ai_status"])
        message = message or res["ai_message"]
        for c in res["conflicts"]:
            cand = c["candidate"]
            db.add(DecisionConflict(
                decision_id=d.id, meeting_id=meeting.id,
                conflicting_decision_id=cand.id if cand.kind == "decision" else None,
                conflicting_doc_id=cand.id if cand.kind == "doc" else None,
                severity=c["severity"], explanation=c["explanation"], suggestion=c["suggestion"],
            ))
            found += 1
            log.warning("decision.conflict_detected", decision_id=d.id, meeting_id=meeting.id,
                        against=f"{cand.kind}:{cand.id}", severity=c["severity"])
    db.commit()
    status = "ok" if statuses == {"ok"} else ("disabled" if "disabled" in statuses else "fallback")
    return {"found": found, "ai_status": status, "ai_message": message}
