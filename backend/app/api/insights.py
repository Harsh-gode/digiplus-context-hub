"""Cross-cutting views: dashboard, conflicts inbox, people, and 'Ask the team memory'."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..logging_setup import get_logger
from ..models import CLOSED_ITEM_STATUSES, ActionItem, DecisionConflict, Meeting, Participant
from ..schemas import AskRequest, AskResult, ConflictOut, ConflictResolve
from ..services import intelligence
from ..services import workflow as wf
from ..services.ai_client import provider_info
from ..services.retrieval import bm25_rank

router = APIRouter(prefix="/api", tags=["insights"])
log = get_logger("api.insights")


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "ai": provider_info()}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    today = date.today()
    items = db.scalars(select(ActionItem)).all()
    open_items = [i for i in items if i.status not in CLOSED_ITEM_STATUSES]
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    def _aware(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    by_owner = defaultdict(lambda: {"open": 0, "overdue": 0})
    for i in open_items:
        key = i.owner or "Unassigned"
        by_owner[key]["open"] += 1
        by_owner[key]["overdue"] += int(wf.is_overdue(i))

    upcoming = db.scalars(
        select(Meeting).where(Meeting.status.in_(["scheduled", "in_progress"])).order_by(Meeting.scheduled_at).limit(5)
    ).all()
    return {
        "counts": {
            "open": len(open_items),
            "overdue": sum(wf.is_overdue(i) for i in open_items),
            "blocked": sum(i.status == "blocked" for i in open_items),
            "unassigned": sum(not i.owner for i in open_items),
            "closed_this_week": sum(1 for i in items if i.closed_at and _aware(i.closed_at) >= week_ago),
            "open_conflicts": len(db.scalars(select(DecisionConflict.id).where(DecisionConflict.status == "open")).all()),
            "meetings": len(db.scalars(select(Meeting.id)).all()),
        },
        "by_owner": sorted(({"owner": k, **v} for k, v in by_owner.items()), key=lambda r: (-r["overdue"], -r["open"])),
        # Items that keep getting carried forward are the ones that silently die.
        "stale": [wf.item_out(i) for i in sorted(open_items, key=lambda i: -i.times_carried) if i.times_carried >= 2][:6],
        "overdue": [wf.item_out(i) for i in sorted(open_items, key=lambda i: i.due_date or today) if wf.is_overdue(i)][:8],
        "upcoming": wf.meeting_summary_rows(db, upcoming),
        "ai": provider_info(),
    }


@router.get("/people")
def people(db: Session = Depends(get_db)):
    names = set(db.scalars(select(Participant.name)).all()) | {o for o in db.scalars(select(ActionItem.owner)).all() if o}
    return sorted(names)


@router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(status: str | None = "open", db: Session = Depends(get_db)):
    return wf.conflicts_for(db, status=status or None)


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictOut)
def resolve_conflict(conflict_id: int, body: ConflictResolve, db: Session = Depends(get_db)):
    c = db.get(DecisionConflict, conflict_id)
    if not c:
        raise HTTPException(404, "Conflict not found")
    if c.status != "open":
        raise HTTPException(409, "Conflict already resolved")
    c.status, c.resolution_note = body.status, body.resolution_note
    db.commit()
    log.info("decision.conflict_resolved", conflict_id=c.id, resolution=body.status)
    return next(x for x in wf.conflicts_for(db, meeting_id=c.meeting_id, status=None) if x.id == c.id)


@router.post("/ask", response_model=AskResult)
def ask(body: AskRequest, db: Session = Depends(get_db)):
    candidates = bm25_rank(body.question, wf.build_corpus(db, include_items=True), top_k=8)
    res = intelligence.ask_memory(body.question, candidates)
    log.info("memory.asked", candidates=len(candidates), sources=len(res["used"]), ai_status=res["ai_status"])
    return AskResult(
        answer=res["answer"],
        sources=[{"key": f"{c.kind}:{c.id}", "kind": c.kind, "id": c.id, "title": c.title} for c in res["used"]],
        ai_status=res["ai_status"], ai_message=res["ai_message"],
    )
