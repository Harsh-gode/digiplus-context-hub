from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..logging_setup import get_logger
from ..models import KnowledgeDoc, KnowledgeLink, Meeting
from ..schemas import DocAnalysis, DocIn, DocOut
from ..services import file_text, intelligence

router = APIRouter(prefix="/api/knowledge", tags=["knowledge base"])
log = get_logger("api.knowledge")


def _clean_tags(tags: list[str]) -> str:
    return ",".join(sorted({t.strip().lower() for t in tags if t.strip()}))


@router.get("", response_model=list[DocOut])
def list_docs(q: str | None = Query(None, max_length=100), db: Session = Depends(get_db)):
    stmt = select(KnowledgeDoc).order_by(KnowledgeDoc.updated_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(KnowledgeDoc.title.ilike(like), KnowledgeDoc.content.ilike(like), KnowledgeDoc.tags.ilike(like)))
    return db.scalars(stmt).all()


@router.post("/analyze", response_model=DocAnalysis)
async def analyze_upload(file: UploadFile = File(...)):
    """Step 1 of an upload: read the file and let AI suggest title, type, tags and a summary. Saves nothing."""
    ex = await file_text.document_text(file)
    ai = intelligence.analyze_document(ex.text, ex.filename)
    log.info("knowledge.file_analyzed", file_kind=ex.kind, pages=ex.pages, chars=len(ex.text),
             truncated=ex.truncated, tags=len(ai["tags"]), ai_status=ai["ai_status"])
    return DocAnalysis(filename=ex.filename, kind=ex.kind, pages=ex.pages, chars=len(ex.text), truncated=ex.truncated,
                       content=ex.text, **ai)


@router.post("", response_model=DocOut, status_code=201)
def create_doc(body: DocIn, db: Session = Depends(get_db)):
    if db.scalar(select(KnowledgeDoc.id).where(KnowledgeDoc.title == body.title)):
        raise HTTPException(409, f"A document titled '{body.title}' already exists")
    doc = KnowledgeDoc(title=body.title, content=body.content, tags=_clean_tags(body.tags), doc_type=body.doc_type)
    db.add(doc)
    db.commit()
    log.info("knowledge.created", doc_id=doc.id, doc_type=doc.doc_type, chars=len(doc.content))
    return doc


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    linked = db.execute(
        select(Meeting.id, Meeting.title, KnowledgeLink.reason).join(KnowledgeLink, KnowledgeLink.meeting_id == Meeting.id)
        .where(KnowledgeLink.doc_id == doc_id)
    ).all()
    return {**DocOut.model_validate(doc).model_dump(), "linked_meetings": [{"id": i, "title": t, "reason": r} for i, t, r in linked]}


@router.put("/{doc_id}", response_model=DocOut)
def update_doc(doc_id: int, body: DocIn, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.title, doc.content, doc.tags, doc.doc_type = body.title, body.content, _clean_tags(body.tags), body.doc_type
    db.commit()
    log.info("knowledge.updated", doc_id=doc.id)
    return doc


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    db.delete(doc)
    db.commit()
    log.info("knowledge.deleted", doc_id=doc_id)
