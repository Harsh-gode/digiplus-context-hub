"""Database schema.

A "Meeting" row represents either a meeting or a work handover (kind field), since both
share the same shape: participants, notes, decisions and action items. Action items keep
their origin meeting and their current meeting, so carrying them forward never loses history.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


MEETING_KINDS = ("meeting", "handover")
MEETING_STATUSES = ("scheduled", "in_progress", "completed", "cancelled")
ITEM_STATUSES = ("open", "in_progress", "blocked", "done", "dropped")
CLOSED_ITEM_STATUSES = ("done", "dropped")
PRIORITIES = ("low", "medium", "high")
NOTE_SOURCES = ("notes", "transcript", "chat", "email", "document")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="meeting")
    title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    agenda: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    summary: Mapped[str] = mapped_column(Text, default="")
    summary_source: Mapped[str] = mapped_column(String(20), default="")  # ai | fallback | manual
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    # For handovers: who is handing over and who takes over.
    handover_from: Mapped[str] = mapped_column(String(120), default="")
    handover_to: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    participants: Mapped[list["Participant"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    notes: Mapped[list["Note"]] = relationship(back_populates="meeting", cascade="all, delete-orphan", order_by="Note.created_at")
    decisions: Mapped[list["Decision"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    previous: Mapped["Meeting | None"] = relationship(remote_side="Meeting.id")


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(80), default="")
    attended: Mapped[bool] = mapped_column(Boolean, default=True)

    meeting: Mapped[Meeting] = relationship(back_populates="participants")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(20), default="notes")
    author: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="notes")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # ai | fallback | manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="decisions")


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    outcome: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # ai | fallback | manual
    origin_meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    current_meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    times_carried: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    history: Mapped[list["ItemHistory"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemHistory.created_at"
    )


class ItemHistory(Base):
    """Audit trail of every change to an action item."""

    __tablename__ = "item_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("action_items.id", ondelete="CASCADE"))
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    event: Mapped[str] = mapped_column(String(40))  # created, status_changed, reassigned, due_changed, carried_forward, closed, reopened
    from_value: Mapped[str] = mapped_column(Text, default="")
    to_value: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[ActionItem] = relationship(back_populates="history")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(300), default="")  # comma separated
    doc_type: Mapped[str] = mapped_column(String(40), default="document")  # document, policy, runbook, spec
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KnowledgeLink(Base):
    """AI-suggested link from a meeting (or one of its items) to a doc or a past meeting."""

    __tablename__ = "knowledge_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("action_items.id", ondelete="CASCADE"), nullable=True)
    doc_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=True)
    linked_meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(20), default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionConflict(Base):
    """Special feature: a new decision that contradicts an earlier decision or a KB document."""

    __tablename__ = "decision_conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"))
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    conflicting_decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), nullable=True)
    conflicting_doc_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low, medium, high
    explanation: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, accepted, dismissed
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
