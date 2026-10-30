from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..logging_setup import get_logger
from ..models import ActionItem, Decision, Meeting, Note, Participant
from ..schemas import (
    ApplyExtract, BriefResult, DecisionIn, ExtractRequest, ExtractResult, ItemCreate, ItemOut, MeetingCreate,
    MeetingDetail, MeetingSummaryOut, MeetingUpdate, NoteIn, ParticipantIn, StatusChange,
)
from ..services import file_text, intelligence
from ..services import workflow as wf

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
log = get_logger("api.meetings")


@router.get("", response_model=list[MeetingSummaryOut])
def list_meetings(
    status: str | None = None, kind: str | None = None, q: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    stmt = select(Meeting).order_by(Meeting.scheduled_at.desc())
    if status:
        stmt = stmt.where(Meeting.status == status)
    if kind:
        stmt = stmt.where(Meeting.kind == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Meeting.title.ilike(like), Meeting.agenda.ilike(like), Meeting.summary.ilike(like)))
    return wf.meeting_summary_rows(db, db.scalars(stmt).all())


@router.post("", response_model=MeetingDetail, status_code=201)
def create_meeting(body: MeetingCreate, db: Session = Depends(get_db)):
    prev = None
    if body.previous_id:
        prev = db.get(Meeting, body.previous_id)
        if not prev:
            raise HTTPException(422, f"Previous meeting {body.previous_id} does not exist")
    if body.kind == "handover" and not body.handover_to.strip():
        raise HTTPException(422, "A handover needs the name of the person taking over (handover_to)")
    names = [p.name.lower() for p in body.participants]
    if len(names) != len(set(names)):
        raise HTTPException(422, "Duplicate participant names")

    m = Meeting(kind=body.kind, title=body.title, scheduled_at=body.scheduled_at, agenda=body.agenda,
                previous_id=body.previous_id, handover_from=body.handover_from.strip(), handover_to=body.handover_to.strip())
    m.participants = [Participant(name=p.name, email=p.email or "", role=p.role, attended=p.attended) for p in body.participants]
    db.add(m)
    db.commit()
    log.info("meeting.created", meeting_id=m.id, kind=m.kind, participants=len(m.participants), previous_id=m.previous_id)

    if prev and body.carry_forward_open_items:
        wf.carry_forward(db, prev, m)
    return wf.meeting_detail(db, wf.get_meeting_or_404(db, m.id))


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    return wf.meeting_detail(db, wf.get_meeting_or_404(db, meeting_id))


@router.patch("/{meeting_id}", response_model=MeetingDetail)
def update_meeting(meeting_id: int, body: MeetingUpdate, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(m, k, v)
    if "summary" in changes:
        m.summary_source = "manual"
    db.commit()
    log.info("meeting.updated", meeting_id=m.id, fields=sorted(changes))
    return wf.meeting_detail(db, m)


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    if db.scalar(select(ActionItem.id).where(ActionItem.origin_meeting_id != m.id, ActionItem.current_meeting_id == m.id).limit(1)):
        raise HTTPException(409, "This meeting holds items carried from earlier meetings; cancel it instead of deleting.")
    db.delete(m)
    db.commit()
    log.info("meeting.deleted", meeting_id=meeting_id)


@router.post("/{meeting_id}/status", response_model=MeetingDetail)
def set_status(meeting_id: int, body: StatusChange, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    wf.change_status(db, m, body.status)
    return wf.meeting_detail(db, m)


@router.post("/{meeting_id}/follow-up", response_model=MeetingDetail, status_code=201)
def create_follow_up(meeting_id: int, body: MeetingCreate, db: Session = Depends(get_db)):
    """Schedule the next meeting in the series; open items move to it automatically."""
    body.previous_id = meeting_id
    return create_meeting(body, db)


@router.post("/{meeting_id}/carry-forward/{target_id}", response_model=list[ItemOut])
def carry_forward_to(meeting_id: int, target_id: int, db: Session = Depends(get_db)):
    src, dst = wf.get_meeting_or_404(db, meeting_id), wf.get_meeting_or_404(db, target_id)
    return [wf.item_out(i) for i in wf.carry_forward(db, src, dst)]


# ---------------------------------------------------------------- children
@router.post("/{meeting_id}/participants", response_model=MeetingDetail, status_code=201)
def add_participant(meeting_id: int, body: ParticipantIn, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    if any(p.name.lower() == body.name.lower() for p in m.participants):
        raise HTTPException(409, f"{body.name} is already a participant")
    m.participants.append(Participant(name=body.name, email=body.email or "", role=body.role, attended=body.attended))
    db.commit()
    return wf.meeting_detail(db, m)


@router.patch("/{meeting_id}/participants/{pid}", response_model=MeetingDetail)
def toggle_attendance(meeting_id: int, pid: int, attended: bool, db: Session = Depends(get_db)):
    p = db.get(Participant, pid)
    if not p or p.meeting_id != meeting_id:
        raise HTTPException(404, "Participant not found")
    p.attended = attended
    db.commit()
    return wf.meeting_detail(db, wf.get_meeting_or_404(db, meeting_id))


@router.delete("/{meeting_id}/participants/{pid}", response_model=MeetingDetail)
def remove_participant(meeting_id: int, pid: int, db: Session = Depends(get_db)):
    p = db.get(Participant, pid)
    if not p or p.meeting_id != meeting_id:
        raise HTTPException(404, "Participant not found")
    db.delete(p)
    db.commit()
    return wf.meeting_detail(db, wf.get_meeting_or_404(db, meeting_id))


@router.post("/{meeting_id}/notes", response_model=MeetingDetail, status_code=201)
def add_note(meeting_id: int, body: NoteIn, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    m.notes.append(Note(content=body.content, source=body.source, author=body.author))
    db.commit()
    log.info("note.added", meeting_id=m.id, source=body.source, chars=len(body.content))
    return wf.meeting_detail(db, m)


@router.delete("/{meeting_id}/notes/{note_id}", response_model=MeetingDetail)
def delete_note(meeting_id: int, note_id: int, db: Session = Depends(get_db)):
    n = db.get(Note, note_id)
    if not n or n.meeting_id != meeting_id:
        raise HTTPException(404, "Note not found")
    db.delete(n)
    db.commit()
    return wf.meeting_detail(db, wf.get_meeting_or_404(db, meeting_id))


@router.post("/{meeting_id}/decisions", response_model=MeetingDetail, status_code=201)
def add_decision(meeting_id: int, body: DecisionIn, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    d = Decision(meeting_id=m.id, text=body.text, rationale=body.rationale, source="manual")
    db.add(d)
    db.commit()
    log.info("decision.created", decision_id=d.id, meeting_id=m.id, source="manual")
    wf.check_conflicts(db, [d], m)
    return wf.meeting_detail(db, m)


@router.delete("/{meeting_id}/decisions/{decision_id}", response_model=MeetingDetail)
def delete_decision(meeting_id: int, decision_id: int, db: Session = Depends(get_db)):
    d = db.get(Decision, decision_id)
    if not d or d.meeting_id != meeting_id:
        raise HTTPException(404, "Decision not found")
    db.delete(d)
    db.commit()
    return wf.meeting_detail(db, wf.get_meeting_or_404(db, meeting_id))


@router.post("/{meeting_id}/items", response_model=ItemOut, status_code=201)
def add_item(meeting_id: int, body: ItemCreate, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    item = wf.create_item(db, m, **body.model_dump(), source="manual")
    db.commit()
    return wf.item_out(item)


# ---------------------------------------------------------------- AI
@router.post("/{meeting_id}/extract", response_model=ExtractResult)
def extract(meeting_id: int, body: ExtractRequest, db: Session = Depends(get_db)):
    """AI step 1: turn raw text into a *draft* recap. Nothing is saved except the raw note; the user reviews then applies."""
    m = wf.get_meeting_or_404(db, meeting_id)
    if body.raw_text and body.raw_text.strip() and body.save_note:
        m.notes.append(Note(content=body.raw_text.strip(), source=body.source))
        db.commit()
    text = body.raw_text.strip() if body.raw_text and body.raw_text.strip() else "\n\n".join(
        f"[{n.source}] {n.content}" for n in m.notes
    )
    if not text.strip():
        raise HTTPException(422, "Nothing to analyse: add notes or paste raw text first")
    result = intelligence.extract_recap(text, m.title, m.scheduled_at, [p.name for p in m.participants], m.agenda)
    log.info("recap.extracted", meeting_id=m.id, ai_status=result["ai_status"], decisions=len(result["decisions"]),
             items=len(result["action_items"]))
    return ExtractResult(**result)


@router.post("/{meeting_id}/transcript", response_model=ExtractResult)
async def upload_transcript(meeting_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a Teams transcript (.vtt / .docx / .txt): save it as a note, add new speakers, return a draft recap."""
    m = wf.get_meeting_or_404(db, meeting_id)
    ex = await file_text.transcript_text(file)

    known = {p.name.lower() for p in m.participants}
    added = []
    for name in ex.speakers:
        if name.lower() not in known and len(m.participants) < 100:
            m.participants.append(Participant(name=name[:120], attended=True, role="from transcript"))
            known.add(name.lower())
            added.append(name)
    m.notes.append(Note(content=ex.text, source="transcript", author=ex.filename))
    db.commit()
    log.info("transcript.uploaded", meeting_id=m.id, file_kind=ex.kind, chars=len(ex.text), speakers=len(ex.speakers),
             speakers_added=len(added), truncated=ex.truncated)

    result = intelligence.extract_recap(ex.text, m.title, m.scheduled_at, [p.name for p in m.participants], m.agenda)
    log.info("recap.extracted", meeting_id=m.id, ai_status=result["ai_status"], decisions=len(result["decisions"]),
             items=len(result["action_items"]), source="transcript")
    return ExtractResult(**result, source_file=ex.filename, speakers=ex.speakers, speakers_added=added)


@router.post("/{meeting_id}/apply-recap", response_model=MeetingDetail)
def apply_recap(meeting_id: int, body: ApplyExtract, db: Session = Depends(get_db)):
    """AI step 2: persist the reviewed recap, then link knowledge and check for decision conflicts."""
    m = wf.get_meeting_or_404(db, meeting_id)
    if body.summary.strip():
        m.summary, m.summary_source = body.summary.strip(), body.source
    new_decisions = []
    for d in body.decisions:
        if d.text.strip():
            dec = Decision(meeting_id=m.id, text=d.text.strip(), rationale=d.rationale, source=body.source)
            db.add(dec)
            new_decisions.append(dec)
    for it in body.action_items:
        if it.title.strip():
            wf.create_item(db, m, title=it.title, owner=it.owner, due_date=it.due_date, priority=it.priority, source=body.source)
    db.commit()
    log.info("recap.applied", meeting_id=m.id, decisions=len(new_decisions), items=len(body.action_items), source=body.source)

    wf.check_conflicts(db, new_decisions, m)
    wf.refresh_links(db, m)
    return wf.meeting_detail(db, m)


@router.post("/{meeting_id}/link-knowledge")
def link_knowledge(meeting_id: int, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    return wf.refresh_links(db, m)


@router.post("/{meeting_id}/check-conflicts")
def recheck_conflicts(meeting_id: int, db: Session = Depends(get_db)):
    m = wf.get_meeting_or_404(db, meeting_id)
    from ..models import DecisionConflict
    db.query(DecisionConflict).filter(DecisionConflict.meeting_id == m.id, DecisionConflict.status == "open").delete()
    db.commit()
    res = wf.check_conflicts(db, list(m.decisions), m)
    return {**res, "conflicts": wf.conflicts_for(db, meeting_id=m.id)}


@router.get("/{meeting_id}/brief", response_model=BriefResult)
def brief(
    meeting_id: int,
    person: str = Query(..., min_length=1, max_length=120),
    reason: str = Query("missed", pattern="^(missed|takeover)$"),
    db: Session = Depends(get_db),
):
    m = wf.get_meeting_or_404(db, meeting_id)
    items = db.scalars(select(ActionItem).where(ActionItem.current_meeting_id == m.id)).all()
    today = date.today()
    struct = [
        {"title": i.title, "owner": i.owner, "status": i.status, "due": str(i.due_date or ""),
         "open": i.status not in ("done", "dropped"), "overdue": wf.is_overdue(i)}
        for i in items
    ]
    prev = db.get(Meeting, m.previous_id) if m.previous_id else None
    ctx = {
        "kind": m.kind, "title": m.title, "date": str(m.scheduled_at.date()), "status": m.status, "summary": m.summary,
        "reader_reason": "is taking over this work" if reason == "takeover" else "missed the meeting",
        "handover": f"{m.handover_from or '?'} -> {m.handover_to}" if m.kind == "handover" else "",
        "attendees": ", ".join(f"{p.name}{'' if p.attended else ' (absent)'}" for p in m.participants) or "unknown",
        "decisions": [d.text for d in m.decisions],
        "items": [
            f"- {i['title']} | owner: {i['owner'] or 'unassigned'} | status: {i['status']} | due: {i['due'] or 'none'}"
            f"{' | OVERDUE' if i['overdue'] else ''}" for i in struct
        ],
        "items_struct": struct,
        "previous": f"{prev.title} ({prev.scheduled_at.date()}): {prev.summary[:500]}" if prev else "",
        "links": [f"{l.title}: {l.reason}" for l in wf.links_for_meeting(db, m.id)[:4]],
        "notes_excerpt": "" if m.summary else "\n".join(n.content for n in m.notes)[:4000],
    }
    res = intelligence.catch_up_brief(person.strip(), ctx)
    mine = [wf.item_out(i) for i in items if i.owner.lower() == person.strip().lower() and i.status not in ("done", "dropped")]
    log.info("brief.generated", meeting_id=m.id, reason=reason, ai_status=res["ai_status"], items_for_reader=len(mine), today=str(today))
    return BriefResult(brief=res["brief"], for_person=person.strip(), open_items_for_person=mine,
                       ai_status=res["ai_status"], ai_message=res["ai_message"])
