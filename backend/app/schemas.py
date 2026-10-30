"""Request/response schemas. All user input is validated here before it reaches the database."""
from datetime import date, datetime, timezone
from typing import Literal

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo; treat naive datetimes as UTC so clients always get an explicit offset."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

MeetingKind = Literal["meeting", "handover"]
MeetingStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]
ItemStatus = Literal["open", "in_progress", "blocked", "done", "dropped"]
Priority = Literal["low", "medium", "high"]
NoteSource = Literal["notes", "transcript", "chat", "email", "document"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _strip_required(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("must not be blank")
    return v


# ---------- Participants ----------
class ParticipantIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    role: str = Field(default="", max_length=80)
    attended: bool = True

    _strip = field_validator("name")(_strip_required)


class ParticipantOut(ORM):
    id: int
    name: str
    email: str
    role: str
    attended: bool


# ---------- Notes ----------
class NoteIn(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)
    source: NoteSource = "notes"
    author: str = Field(default="", max_length=120)

    _strip = field_validator("content")(_strip_required)


class NoteOut(ORM):
    id: int
    content: str
    source: str
    author: str
    created_at: UTCDateTime


# ---------- Decisions ----------
class DecisionIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    rationale: str = Field(default="", max_length=4000)

    _strip = field_validator("text")(_strip_required)


class DecisionOut(ORM):
    id: int
    meeting_id: int
    text: str
    rationale: str
    source: str
    created_at: UTCDateTime


# ---------- Action items ----------
class ItemCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=4000)
    owner: str = Field(default="", max_length=120)
    due_date: date | None = None
    priority: Priority = "medium"

    _strip = field_validator("title")(_strip_required)


class ItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    status: Literal["open", "in_progress", "blocked"] | None = None
    priority: Priority | None = None
    note: str = Field(default="", max_length=1000, description="Optional comment recorded in history")


class ItemClose(BaseModel):
    status: Literal["done", "dropped"] = "done"
    outcome: str = Field(min_length=5, max_length=4000, description="What actually happened")

    _strip = field_validator("outcome")(_strip_required)


class HistoryOut(ORM):
    id: int
    event: str
    from_value: str
    to_value: str
    note: str
    meeting_id: int | None
    created_at: UTCDateTime


class ItemOut(ORM):
    id: int
    title: str
    description: str
    owner: str
    due_date: date | None
    status: str
    priority: str
    outcome: str
    source: str
    origin_meeting_id: int
    current_meeting_id: int
    times_carried: int
    created_at: UTCDateTime
    updated_at: UTCDateTime
    closed_at: UTCDateTime | None
    is_overdue: bool = False


class ItemDetail(ItemOut):
    history: list[HistoryOut] = []
    origin_meeting_title: str = ""
    current_meeting_title: str = ""


# ---------- Meetings ----------
class MeetingCreate(BaseModel):
    kind: MeetingKind = "meeting"
    title: str = Field(min_length=3, max_length=200)
    scheduled_at: UTCDateTime
    agenda: str = Field(default="", max_length=10_000)
    participants: list[ParticipantIn] = Field(default_factory=list, max_length=100)
    previous_id: int | None = None
    carry_forward_open_items: bool = True
    handover_from: str = Field(default="", max_length=120)
    handover_to: str = Field(default="", max_length=120)

    _strip = field_validator("title")(_strip_required)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    scheduled_at: UTCDateTime | None = None
    agenda: str | None = Field(default=None, max_length=10_000)
    summary: str | None = Field(default=None, max_length=20_000)
    handover_from: str | None = Field(default=None, max_length=120)
    handover_to: str | None = Field(default=None, max_length=120)


class StatusChange(BaseModel):
    status: MeetingStatus


class MeetingSummaryOut(ORM):
    id: int
    kind: str
    title: str
    scheduled_at: UTCDateTime
    status: str
    previous_id: int | None
    handover_from: str
    handover_to: str
    participant_count: int = 0
    open_item_count: int = 0
    open_conflicts: int = 0


class LinkOut(BaseModel):
    id: int
    item_id: int | None
    doc_id: int | None
    linked_meeting_id: int | None
    title: str
    reason: str
    score: float
    source: str


class ConflictOut(BaseModel):
    id: int
    decision_id: int
    decision_text: str
    meeting_id: int
    conflicting_decision_id: int | None
    conflicting_text: str
    conflicting_source_title: str
    conflicting_meeting_id: int | None
    conflicting_doc_id: int | None
    severity: str
    explanation: str
    suggestion: str
    status: str
    resolution_note: str
    created_at: UTCDateTime


class MeetingDetail(ORM):
    id: int
    kind: str
    title: str
    scheduled_at: UTCDateTime
    agenda: str
    status: str
    summary: str
    summary_source: str
    previous_id: int | None
    previous_title: str = ""
    next_id: int | None = None
    handover_from: str
    handover_to: str
    created_at: UTCDateTime
    updated_at: UTCDateTime
    participants: list[ParticipantOut]
    notes: list[NoteOut]
    decisions: list[DecisionOut]
    items: list[ItemOut] = []
    links: list[LinkOut] = []
    conflicts: list[ConflictOut] = []


# ---------- Knowledge ----------
class DocIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    doc_type: Literal["document", "policy", "runbook", "spec", "note"] = "document"

    _strip = field_validator("title", "content")(_strip_required)


class DocOut(ORM):
    id: int
    title: str
    content: str
    tags: list[str]
    doc_type: str
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @field_validator("tags", mode="before")
    @classmethod
    def split_tags(cls, v):
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


# ---------- AI ----------
class ExtractRequest(BaseModel):
    raw_text: str | None = Field(default=None, max_length=50_000, description="Extra text to analyse; defaults to the meeting's notes")
    source: NoteSource = "notes"
    save_note: bool = True


class ExtractedItem(BaseModel):
    title: str
    owner: str = ""
    due_date: date | None = None
    priority: Priority = "medium"


class ExtractedDecision(BaseModel):
    text: str
    rationale: str = ""


class ExtractResult(BaseModel):
    summary: str
    decisions: list[ExtractedDecision]
    action_items: list[ExtractedItem]
    open_questions: list[str] = []
    ai_status: str  # ok | fallback | disabled
    ai_message: str = ""
    # Filled when the recap came from an uploaded transcript
    source_file: str = ""
    speakers: list[str] = []
    speakers_added: list[str] = []


class DocAnalysis(BaseModel):
    """AI suggestions for an uploaded file. Nothing is saved until the user confirms."""
    filename: str
    kind: str
    pages: int
    chars: int
    truncated: bool
    content: str
    title: str
    doc_type: str
    tags: list[str]
    summary: str
    ai_status: str
    ai_message: str = ""


class ApplyExtract(BaseModel):
    summary: str = Field(default="", max_length=20_000)
    decisions: list[ExtractedDecision] = Field(default_factory=list, max_length=50)
    action_items: list[ExtractedItem] = Field(default_factory=list, max_length=100)
    source: Literal["ai", "fallback", "manual"] = "ai"


class BriefResult(BaseModel):
    brief: str
    for_person: str
    open_items_for_person: list[ItemOut] = []
    ai_status: str
    ai_message: str = ""


class ConflictResolve(BaseModel):
    resolution_note: str = Field(default="", max_length=2000)
    status: Literal["accepted", "dismissed"]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

    _strip = field_validator("question")(_strip_required)


class AskResult(BaseModel):
    answer: str
    sources: list[dict]
    ai_status: str
    ai_message: str = ""
