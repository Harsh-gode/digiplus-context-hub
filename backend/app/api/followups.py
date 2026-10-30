from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..logging_setup import get_logger
from ..models import CLOSED_ITEM_STATUSES, ActionItem
from ..services import followup
from ..services import workflow as wf

router = APIRouter(prefix="/api/followups", tags=["follow-up autopilot"])
log = get_logger("api.followups")


class NudgeRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=120)
    item_ids: list[int] = Field(default_factory=list, max_length=20, description="Empty = owner's medium/high-risk items")
    tone: Literal["friendly", "firm"] = "friendly"
    channel: Literal["slack", "email"] = "slack"
    sender: str = Field(default="", max_length=120)


class SentRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=120)
    item_ids: list[int] = Field(min_length=1, max_length=20)
    channel: Literal["slack", "email"] = "slack"


@router.get("")
def board(db: Session = Depends(get_db)):
    """Open items grouped by owner with a 0-100 slip-risk score and the reasons behind it."""
    data = followup.build_board(db)
    log.info("followup.board_built", open=data["summary"]["open"], high=data["summary"]["high"])
    return data


@router.post("/draft")
def draft(body: NudgeRequest, db: Session = Depends(get_db)):
    owner = next((o for o in followup.build_board(db)["owners"] if o["owner"] == body.owner), None)
    if not owner:
        raise HTTPException(404, f"{body.owner} has no open items")
    items = [i for i in owner["items"] if i["id"] in body.item_ids] if body.item_ids else \
        [i for i in owner["items"] if i["level"] != "low"] or owner["items"][:3]
    if not items:
        raise HTTPException(422, "None of those items are open for this person")
    res = followup.draft_nudge(body.owner, items[:8], body.tone, body.channel, body.sender)
    log.info("followup.nudge_drafted", items=len(items), tone=body.tone, channel=body.channel, ai_status=res["ai_status"])
    return {**res, "owner": body.owner, "email": owner["email"], "item_ids": [i["id"] for i in items[:8]]}


@router.post("/sent")
def mark_sent(body: SentRequest, db: Session = Depends(get_db)):
    """Record that the follow-up went out: a `nudged` event in each item's history."""
    items = db.scalars(select(ActionItem).where(ActionItem.id.in_(body.item_ids))).all()
    valid = [i for i in items if i.owner == body.owner and i.status not in CLOSED_ITEM_STATUSES]
    if not valid:
        raise HTTPException(422, "No open items for this person in that list")
    for i in valid:
        wf.add_history(db, i, "nudged", to_value=body.owner, note=f"Follow-up sent via {body.channel}")
    db.commit()
    log.info("followup.nudge_sent", items=len(valid), channel=body.channel)
    return {"recorded": len(valid)}
