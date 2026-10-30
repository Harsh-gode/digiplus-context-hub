"""AI features: recap extraction, catch-up briefs, knowledge linking, conflict detection, Q&A.

Each feature follows the same pattern:
  1. build a compact prompt (only the data the task needs, truncated),
  2. call the model and validate the JSON shape,
  3. if the AI is disabled or fails, return a deterministic rule-based fallback and say so.
"""
import re
from datetime import date, datetime, timedelta

from pydantic import ValidationError

from ..logging_setup import get_logger
from ..schemas import ExtractedDecision, ExtractedItem
from .ai_client import call_json
from .retrieval import Candidate, tokenize

log = get_logger("intelligence")

MAX_INPUT_CHARS = 14_000


def _require_str(key: str):
    """Build a validator that checks the AI JSON has a non-empty string under `key`."""
    def check(data: dict) -> None:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"'{key}' missing from AI output")
    return check


def _clip(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n…[truncated]"


# ============================================================================
# 1. Raw notes -> structured recap
# ============================================================================
EXTRACT_SYSTEM = """You are a meticulous meeting secretary for an IT services company.
Turn raw, messy input (notes, transcripts, chat logs, emails) into a structured recap.
Rules:
- Only include decisions that were actually agreed, not ideas that were merely discussed.
- Action items must be concrete tasks. Owner must be a person named in the text or participant list; use "" if unclear — never invent people.
- Resolve relative dates ("by Friday", "next week") against the meeting date. Use ISO format YYYY-MM-DD or null.
- priority is one of low, medium, high (high = blocking, customer-facing or urgent).
- Summary: 2-4 sentences, plain language, what happened and why it matters.
- open_questions: unresolved questions or risks raised but not answered.
Return JSON: {"summary": str, "decisions": [{"text": str, "rationale": str}],
"action_items": [{"title": str, "owner": str, "due_date": str|null, "priority": str}], "open_questions": [str]}"""


def _validate_extract(data: dict) -> None:
    if not isinstance(data.get("summary"), str):
        raise ValueError("summary missing")
    [ExtractedDecision(**d) for d in data.get("decisions", [])]
    [ExtractedItem(**i) for i in data.get("action_items", [])]


def extract_recap(text: str, meeting_title: str, meeting_date: datetime, participants: list[str], agenda: str = "") -> dict:
    user = (
        f"Meeting: {meeting_title}\nMeeting date: {meeting_date.date().isoformat()} ({meeting_date.strftime('%A')})\n"
        f"Participants: {', '.join(participants) or 'unknown'}\nAgenda:\n{_clip(agenda, 2000) or '(none)'}\n\n"
        f"--- RAW INPUT ---\n{_clip(text)}"
    )
    result = call_json("extract_recap", EXTRACT_SYSTEM, user, validate=_validate_extract)
    if result.data:
        try:
            decisions = [ExtractedDecision(**d) for d in result.data.get("decisions", [])]
            items = []
            for raw in result.data.get("action_items", []):
                try:
                    item = ExtractedItem(**raw)
                except ValidationError:
                    item = ExtractedItem(title=str(raw.get("title", "")), owner=str(raw.get("owner") or ""))
                if item.title.strip():
                    items.append(item)
            return {
                "summary": result.data["summary"].strip(),
                "decisions": decisions,
                "action_items": items,
                "open_questions": [str(q) for q in result.data.get("open_questions", [])][:10],
                "ai_status": "ok",
                "ai_message": "",
            }
        except (ValidationError, KeyError, TypeError) as e:
            log.warning("ai.output_invalid", task="extract_recap", error=str(e)[:200])
            result.status, result.message = "fallback", "AI output did not match the expected format; used rule-based extraction."

    fb = fallback_extract(text, meeting_date, participants)
    fb.update(ai_status=result.status, ai_message=result.message)
    return fb


_DECISION_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?:decision|decided|agreed|we will|resolution|approved)\b[:\s-]*(.+)", re.I)
_ACTION_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\[ \]\s*|todo[:\s]|action(?: item)?[:\s]|ai[:\s]|follow[- ]up[:\s])\s*(.+)", re.I
)
_WILL_RE = re.compile(r"^\s*(?:[-*•]\s*)?([A-Z][a-z]+)\s+(?:will|to|should|must|needs to)\s+(.+)")
_OWNER_AT_RE = re.compile(r"@([A-Za-z]+)")
_ISO_DATE_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _guess_due(text: str, base: date) -> date | None:
    m = _ISO_DATE_RE.search(text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    low = text.lower()
    if "tomorrow" in low:
        return base + timedelta(days=1)
    if "end of week" in low or "eow" in low:
        return base + timedelta(days=(4 - base.weekday()) % 7)
    if "next week" in low:
        return base + timedelta(days=7)
    for i, day in enumerate(_WEEKDAYS):
        if re.search(rf"\b(by|on|before)\s+{day}\b", low):
            delta = (i - base.weekday()) % 7 or 7
            return base + timedelta(days=delta)
    return None


def _guess_owner(text: str, participants: list[str]) -> str:
    m = _OWNER_AT_RE.search(text)
    if m:
        for p in participants:
            if p.lower().startswith(m.group(1).lower()):
                return p
        return m.group(1)
    low = text.lower()
    for p in participants:
        first = p.split()[0].lower()
        if re.search(rf"\b{re.escape(first)}\b", low):
            return p
    return ""


def fallback_extract(text: str, meeting_date: datetime, participants: list[str]) -> dict:
    """Deterministic extraction from common note-taking conventions."""
    decisions, items = [], []
    base = meeting_date.date()
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        if m := _DECISION_RE.match(line):
            decisions.append(ExtractedDecision(text=m.group(1).strip().rstrip(".") + "."))
            continue
        action = None
        if m := _ACTION_RE.match(line):
            action = m.group(1).strip()
        elif (m := _WILL_RE.match(line)) and any(p.split()[0] == m.group(1) for p in participants):
            action = line.strip(" -*•")
        if action:
            items.append(
                ExtractedItem(
                    title=action[:300],
                    owner=_guess_owner(action, participants),
                    due_date=_guess_due(action, base),
                    priority="high" if re.search(r"urgent|asap|blocker|critical|p0|p1", action, re.I) else "medium",
                )
            )
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip())
    summary = " ".join(sentences[:3])[:600] if sentences and sentences[0] else "No notes yet."
    return {
        "summary": summary,
        "decisions": decisions,
        "action_items": items,
        "open_questions": [l.strip(" -*•") for l in (text or "").splitlines() if l.strip().endswith("?")][:5],
    }


# ============================================================================
# 2. Catch-up brief for someone who missed the meeting / is taking over
# ============================================================================
BRIEF_SYSTEM = """You write short catch-up briefs for colleagues who missed a meeting or are taking over work.
Write for the named reader. Be concrete and skimmable; no filler, no greetings.
Structure (markdown):
**TL;DR** – one or two sentences.
**What was decided** – bullets.
**What you own now** – bullets with due dates; say "Nothing assigned to you" if none.
**Open items to watch** – bullets for other open/blocked/overdue items, with owners.
**Context you need** – 1-3 bullets of background (history, carried-over items, linked docs).
Keep it under 250 words. Only use facts from the input. Return JSON: {"brief": "<markdown>"}"""


def catch_up_brief(person: str, context: dict) -> dict:
    lines = [
        f"Reader: {person} ({context.get('reader_reason', 'missed the meeting')})",
        f"Today: {date.today().isoformat()}",
        f"{context['kind'].title()}: {context['title']} on {context['date']} (status: {context['status']})",
    ]
    if context.get("handover"):
        lines.append(f"Handover: {context['handover']}")
    lines.append(f"Attendees: {context['attendees']}")
    lines.append(f"Summary: {context['summary'] or '(none)'}")
    lines.append("Decisions:\n" + ("\n".join(f"- {d}" for d in context["decisions"]) or "- none"))
    lines.append("Action items:\n" + ("\n".join(context["items"]) or "- none"))
    if context.get("previous"):
        lines.append(f"Previous session: {context['previous']}")
    if context.get("links"):
        lines.append("Related knowledge:\n" + "\n".join(f"- {l}" for l in context["links"]))
    if context.get("notes_excerpt"):
        lines.append("Raw notes excerpt:\n" + _clip(context["notes_excerpt"], 4000))
    user = "\n".join(lines)

    result = call_json(
        "catch_up_brief", BRIEF_SYSTEM, user,
        validate=_require_str("brief"),
    )
    if result.data:
        return {"brief": result.data["brief"].strip(), "ai_status": "ok", "ai_message": ""}
    return {"brief": fallback_brief(person, context), "ai_status": result.status, "ai_message": result.message}


def fallback_brief(person: str, ctx: dict) -> str:
    mine = [i for i in ctx["items_struct"] if i["owner"].lower() == person.lower() and i["open"]]
    others = [i for i in ctx["items_struct"] if i["open"] and i not in mine]
    out = [f"**TL;DR** – {ctx['title']} ({ctx['date']}). {ctx['summary'] or 'No summary recorded yet.'}", "", "**What was decided**"]
    out += [f"- {d}" for d in ctx["decisions"]] or ["- No decisions recorded."]
    out += ["", "**What you own now**"]
    out += [f"- {i['title']} (due {i['due'] or 'no date'}, {i['status']})" for i in mine] or ["- Nothing assigned to you."]
    out += ["", "**Open items to watch**"]
    out += [f"- {i['title']} — {i['owner'] or 'unassigned'} ({i['status']}{', OVERDUE' if i['overdue'] else ''})" for i in others[:8]] or ["- None."]
    if ctx.get("links"):
        out += ["", "**Context you need**"] + [f"- {l}" for l in ctx["links"][:3]]
    return "\n".join(out)


# ============================================================================
# 3. Link a meeting and its items to the knowledge base
# ============================================================================
LINK_SYSTEM = """You connect meeting content to a team knowledge base.
Given a meeting (summary, decisions, action items) and candidate documents/past meetings (pre-filtered by keyword search),
select only candidates that are genuinely useful context. For each, explain in one sentence WHY it is relevant
(e.g. "Defines the SLA the escalation decision depends on"). If a candidate relates to one specific action item, give its item_id.
Score relevance 0.0-1.0. Skip weak or coincidental matches.
Return JSON: {"links": [{"candidate_key": str, "item_id": int|null, "reason": str, "score": float}]}"""


def link_knowledge(meeting_text: str, items: list[dict], candidates: list[Candidate]) -> dict:
    if not candidates:
        return {"links": [], "ai_status": "ok", "ai_message": "No related documents found."}
    keyed = {f"{c.kind}:{c.id}": c for c in candidates}
    cand_text = "\n\n".join(f"[{k}] {c.title}\n{_clip(c.text, 900)}" for k, c in keyed.items())
    item_text = "\n".join(f"- item_id={i['id']}: {i['title']} (owner {i['owner'] or '?'})" for i in items) or "- none"
    user = f"MEETING:\n{_clip(meeting_text, 5000)}\n\nACTION ITEMS:\n{item_text}\n\nCANDIDATES:\n{cand_text}"

    def _validate(d):
        if not isinstance(d.get("links"), list):
            raise ValueError("links missing")

    result = call_json("link_knowledge", LINK_SYSTEM, user, validate=_validate)
    valid_items = {i["id"] for i in items}
    if result.data:
        links = []
        for l in result.data["links"]:
            c = keyed.get(str(l.get("candidate_key", "")))
            if not c:
                continue  # model referenced something we didn't give it -> ignore
            item_id = l.get("item_id") if l.get("item_id") in valid_items else None
            try:
                score = max(0.0, min(1.0, float(l.get("score", 0.5))))
            except (TypeError, ValueError):
                score = 0.5
            links.append({"candidate": c, "item_id": item_id, "reason": str(l.get("reason", ""))[:500], "score": score, "source": "ai"})
        return {"links": links, "ai_status": "ok", "ai_message": ""}

    top = max(c.score for c in candidates) or 1
    links = [
        {
            "candidate": c,
            "item_id": None,
            "reason": f"Keyword match: {', '.join(c.matched_terms[:4])}.",
            "score": round(c.score / top, 2),
            "source": "fallback",
        }
        for c in candidates[:4]
        if c.score / top >= 0.35
    ]
    return {"links": links, "ai_status": result.status, "ai_message": result.message}


# ============================================================================
# 4. SPECIAL FEATURE: decision conflict detector
# ============================================================================
CONFLICT_SYSTEM = """You are a "decision memory" guard for a team. A new decision was just recorded.
Compare it with earlier decisions and knowledge-base documents (pre-filtered as possibly related).
Flag ONLY genuine conflicts: the new decision contradicts, reverses, or violates an earlier decision or a documented
policy/standard, or two decisions cannot both be true. Do NOT flag decisions that merely refine, extend or agree.
severity: high = violates a policy/commitment or reverses a decision others depend on; medium = partial contradiction; low = possible tension.
suggestion: one sentence on how to resolve (e.g. "Confirm with the owner of the 12 Oct decision and update the runbook").
Return JSON: {"conflicts": [{"candidate_key": str, "severity": str, "explanation": str, "suggestion": str}]} — empty list if none."""

_NEGATION_PAIRS = [
    ("aws", "azure"), ("aws", "gcp"), ("azure", "gcp"), ("monthly", "weekly"), ("weekly", "daily"),
    ("postgres", "mysql"), ("postgresql", "mongodb"), ("react", "angular"), ("approve", "reject"),
    ("allow", "block"), ("enable", "disable"), ("in-house", "outsource"), ("remote", "onsite"),
]


def detect_conflicts(decision_text: str, meeting_title: str, candidates: list[Candidate]) -> dict:
    if not candidates:
        return {"conflicts": [], "ai_status": "ok", "ai_message": ""}
    keyed = {f"{c.kind}:{c.id}": c for c in candidates}
    cand_text = "\n\n".join(
        f"[{k}] ({'decision from ' + c.meta.get('meeting_title', '') + ' on ' + c.meta.get('date', '') if c.kind == 'decision' else 'document: ' + c.title})\n{_clip(c.text, 1200)}"
        for k, c in keyed.items()
    )
    user = f"NEW DECISION (from '{meeting_title}'):\n{decision_text}\n\nEARLIER DECISIONS AND DOCUMENTS:\n{cand_text}"

    def _validate(d):
        if not isinstance(d.get("conflicts"), list):
            raise ValueError("conflicts missing")

    result = call_json("detect_conflicts", CONFLICT_SYSTEM, user, validate=_validate)
    if result.data:
        out = []
        for c in result.data["conflicts"]:
            cand = keyed.get(str(c.get("candidate_key", "")))
            if not cand:
                continue
            sev = c.get("severity") if c.get("severity") in ("low", "medium", "high") else "medium"
            out.append({"candidate": cand, "severity": sev, "explanation": str(c.get("explanation", ""))[:1000],
                        "suggestion": str(c.get("suggestion", ""))[:500]})
        return {"conflicts": out, "ai_status": "ok", "ai_message": ""}

    # Fallback: same topic + mutually exclusive terms on each side -> low-severity "possible" conflict.
    new_terms = set(tokenize(decision_text))
    out = []
    for cand in candidates[:5]:
        old_terms = set(tokenize(cand.text))
        pair_terms = {t for pair in _NEGATION_PAIRS for t in pair}
        if not (new_terms & old_terms) - pair_terms:
            continue  # not about the same topic
        for a, b in _NEGATION_PAIRS:
            if (a in new_terms and b in old_terms and b not in new_terms) or (b in new_terms and a in old_terms and a not in new_terms):
                out.append({
                    "candidate": cand, "severity": "low",
                    "explanation": f"Possible conflict (rule-based): this decision mentions '{a if a in new_terms else b}' while the earlier one mentions '{b if a in new_terms else a}' on the same topic.",
                    "suggestion": "Check whether the earlier decision is being intentionally replaced.",
                })
                break
    return {"conflicts": out, "ai_status": result.status, "ai_message": result.message}


# ============================================================================
# 5. Ask the team memory (Q&A with citations)
# ============================================================================
ASK_SYSTEM = """Answer the question using ONLY the provided sources from the team's meetings, decisions, items and documents.
Cite sources inline as [key]. If the sources don't contain the answer, say so plainly. Be concise (under 150 words).
Return JSON: {"answer": str, "used_keys": [str]}"""


def ask_memory(question: str, candidates: list[Candidate]) -> dict:
    if not candidates:
        return {"answer": "I couldn't find anything in meetings or the knowledge base about that.", "used": [], "ai_status": "ok", "ai_message": ""}
    keyed = {f"{c.kind}:{c.id}": c for c in candidates}
    ctx = "\n\n".join(f"[{k}] {c.title}\n{_clip(c.text, 1200)}" for k, c in keyed.items())
    result = call_json("ask_memory", ASK_SYSTEM, f"QUESTION: {question}\n\nSOURCES:\n{ctx}",
                       validate=_require_str("answer"))
    if result.data:
        used = [keyed[k] for k in result.data.get("used_keys", []) if k in keyed] or candidates[:3]
        return {"answer": result.data["answer"], "used": used, "ai_status": "ok", "ai_message": ""}
    best = candidates[:3]
    answer = "AI is unavailable, so here are the most relevant records I found:\n" + "\n".join(
        f"- [{c.kind}:{c.id}] {c.title}: {_clip(' '.join(c.text.split()), 220)}" for c in best
    )
    return {"answer": answer, "used": best, "ai_status": result.status, "ai_message": result.message}
