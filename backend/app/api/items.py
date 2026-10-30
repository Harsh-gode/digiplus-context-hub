from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CLOSED_ITEM_STATUSES, ActionItem
from ..schemas import ItemClose, ItemDetail, ItemOut, ItemUpdate
from ..services import workflow as wf

router = APIRouter(prefix="/api/items", tags=["action items"])


@router.get("", response_model=list[ItemOut])
def list_items(
    status: str | None = Query(None, description="open | closed | any single status"),
    owner: str | None = Query(None, max_length=120),
    overdue: bool = False,
    due_within_days: int | None = Query(None, ge=0, le=365),
    q: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    stmt = select(ActionItem)
    if status == "open":
        stmt = stmt.where(ActionItem.status.not_in(CLOSED_ITEM_STATUSES))
    elif status == "closed":
        stmt = stmt.where(ActionItem.status.in_(CLOSED_ITEM_STATUSES))
    elif status:
        stmt = stmt.where(ActionItem.status == status)
    if owner is not None:
        stmt = stmt.where(ActionItem.owner == owner) if owner else stmt.where(ActionItem.owner == "")
    if overdue:
        stmt = stmt.where(ActionItem.due_date < date.today(), ActionItem.status.not_in(CLOSED_ITEM_STATUSES))
    if due_within_days is not None:
        stmt = stmt.where(ActionItem.due_date <= date.today() + timedelta(days=due_within_days))
    if q:
        stmt = stmt.where(or_(ActionItem.title.ilike(f"%{q}%"), ActionItem.description.ilike(f"%{q}%")))
    stmt = stmt.order_by(ActionItem.due_date.is_(None), ActionItem.due_date, ActionItem.id)
    return [wf.item_out(i) for i in db.scalars(stmt).all()]


@router.get("/{item_id}", response_model=ItemDetail)
def get_item(item_id: int, db: Session = Depends(get_db)):
    return wf.item_detail(db, wf.get_item_or_404(db, item_id))


@router.patch("/{item_id}", response_model=ItemDetail)
def update_item(item_id: int, body: ItemUpdate, db: Session = Depends(get_db)):
    item = wf.get_item_or_404(db, item_id)
    changes = body.model_dump(exclude_unset=True, exclude={"note"})
    if not changes:
        raise HTTPException(422, "No changes supplied")
    if "owner" in changes and changes["owner"] is not None:
        changes["owner"] = changes["owner"].strip()
    wf.update_item(db, item, changes, body.note)
    return wf.item_detail(db, item)


@router.post("/{item_id}/close", response_model=ItemDetail)
def close_item(item_id: int, body: ItemClose, db: Session = Depends(get_db)):
    item = wf.get_item_or_404(db, item_id)
    wf.close_item(db, item, body.status, body.outcome)
    return wf.item_detail(db, item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = wf.get_item_or_404(db, item_id)
    db.delete(item)
    db.commit()
