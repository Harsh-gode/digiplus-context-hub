# DigiPlus Context Hub

**AI-powered knowledge & task management for teams that lose context when work changes hands.**

Paste messy notes, a chat export, an email thread or a transcript → get a reviewed recap (summary, decisions, action items with owners and due dates) → track every item until it is closed with a recorded outcome → carry open items forward to the next meeting with full history → give anyone who missed it, or is taking over, a personalised catch-up brief.

---

## Features

| Requirement | How it's met |
|---|---|
| Create & persist meetings / work transfers | `Meeting` with `kind = meeting | handover`, agenda, participants (with attendance), raw notes, decisions, action items. Handovers record *from* → *to*. |
| Lifecycle | Meetings: `scheduled → in_progress → completed / cancelled` (enforced transitions, reopen allowed). Items: `open → in_progress / blocked → done / dropped`. |
| Track action items | Owner, due date, priority, status, overdue flag; filter by owner/status/overdue; side-panel editor. |
| Carry forward with history | "Follow-up" creates the next meeting in the series and moves every open item. Each item keeps `origin_meeting_id`, `current_meeting_id`, `times_carried`, and an `item_history` audit trail (created, reassigned, status/due changes, carried_forward, closed, reopened). |
| AI → structured recap | `/extract` returns a **draft**; the user edits it, then `/apply-recap` saves it. AI never writes to the DB unreviewed. |
| Catch-up brief | Personalised to the reader ("missed it" vs "taking over"): TL;DR, decisions, *what you own now*, items to watch, context. |
| Knowledge base + AI linking | CRUD for team docs/policies/runbooks. Past meetings also count as knowledge. Links include a one-line *why it's relevant*. |
| Record outcomes | Closing an item **requires** an outcome (≥5 chars), stored and shown in history. |
| Validation & errors | Pydantic validation on every input, business-rule checks (409 for illegal transitions, duplicates, closing twice), consistent error JSON with `request_id`, UI toasts that show the request ID. |
| Structured logging | See [Logging](#logging). |
| Special features | **Decision Conflict Detector**, **Follow-up Autopilot** (slip-risk scores + AI nudges), "Going stale" tracking. See [below](#special-feature-decision-conflict-detector). |
| Bonus | "Ask the team memory" – Q&A over meetings, decisions, items and docs, answers cite sources. |

## Architecture

```
React (Vite, Tailwind) ──fetch /api──▶ FastAPI ──▶ SQLAlchemy ──▶ PostgreSQL (prod) / SQLite (dev)
                                          │
                                          ├─ services/workflow.py      lifecycle, carry-forward, history, orchestration
                                          ├─ services/intelligence.py  prompts + validation + rule-based fallbacks
                                          ├─ services/ai_client.py     provider-agnostic JSON client (Gemini / Claude / OpenAI)
                                          └─ services/retrieval.py     BM25 keyword retrieval (no external service)
```

One Docker container serves both API and built UI → one URL, no CORS issues, simple deploy.

**Why these choices**
- **FastAPI + Pydantic**: the same models validate user input *and* the AI's JSON output.
- **Retrieve-then-reason**: BM25 shortlists ~6–8 candidates, then the LLM reasons over only those. Keeps prompts small and cheap, makes AI answers checkable, and means linking still works (keyword-only) when AI is down.
- **Human-in-the-loop**: AI produces drafts; people confirm. Every AI-generated record is tagged `source = ai | fallback | manual` and shown in the UI.

### Data model

`meetings` (kind, status, previous_id → series chain, handover_from/to) · `participants` (attended) · `notes` (raw input + source type) · `decisions` · `action_items` (origin/current meeting, times_carried, outcome, closed_at) · `item_history` (audit trail) · `knowledge_docs` · `knowledge_links` (meeting/item → doc or past meeting, reason, score) · `decision_conflicts` (decision ↔ earlier decision or doc, severity, explanation, suggestion, resolution).

### API (OpenAPI docs at `/docs`)

```
GET/POST   /api/meetings                    list (filter kind/status/q) / create (optionally carry items from previous_id)
GET/PATCH/DELETE /api/meetings/{id}
POST       /api/meetings/{id}/status        lifecycle transition (validated)
POST       /api/meetings/{id}/follow-up     next meeting in series + carry open items
POST       /api/meetings/{id}/extract       AI: raw text → draft recap
POST       /api/meetings/{id}/apply-recap   save reviewed recap → auto conflict check + knowledge linking
GET        /api/meetings/{id}/brief?person=&reason=missed|takeover
POST       /api/meetings/{id}/link-knowledge | /check-conflicts
POST       /api/meetings/{id}/participants | notes | decisions | items
GET        /api/items?status=open|closed|…&owner=&overdue=true&q=
GET/PATCH  /api/items/{id}                  edit / reassign (history recorded)
POST       /api/items/{id}/close            requires outcome
CRUD       /api/knowledge
GET        /api/dashboard · /api/conflicts · /api/people · /api/health
POST       /api/conflicts/{id}/resolve      accepted (intentional change) | dismissed
POST       /api/ask                         Q&A with citations
```

## AI configuration

Set **one** key; the provider is auto-detected (or force it with `AI_PROVIDER`).

| Provider | Env vars | Default model |
|---|---|---|
| Google Gemini (free tier available) | `GEMINI_API_KEY` | `gemini-3.6-flash`, falling back to `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-flash` on 404 |
| Anthropic Claude | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |

Also: `AI_TIMEOUT_SECONDS` (30), `AI_MAX_RETRIES` (1).

**Data flow & prompts** (`services/intelligence.py`): each task has a focused system prompt, temperature 0.2, JSON-only output. Inputs are truncated (~14k chars) and only the fields a task needs are sent.

**Reliability**
1. Responses are parsed tolerantly (handles ```json fences / surrounding prose).
2. Shape is validated with Pydantic; invalid output counts as a failed attempt and is **retried**.
3. Non-retryable errors (401/403/404 bad key or model) fail fast.
4. On failure the user gets a **rule-based fallback** (regex extraction of `Decision:` / `Action:` / `TODO` / `@name` / "X will…", relative dates like "by Friday"; templated brief; keyword links) and a visible amber banner – the app never breaks.
5. AI references are checked against what it was given: a link or conflict pointing to a document id that wasn't in the candidate list is discarded (no hallucinated references).
6. The app runs fully with **no key** (`AI offline` badge in the sidebar).

## Data source

On first start the DB is seeded (`app/seed.py`) with a realistic, fictional scenario: DigiPlus delivering a **Northwind Bank customer portal**. It includes a 4-meeting weekly series (with items carried 1–3×), a handover (Rahul → Sneha before leave, with reassigned items), a security review, 11 action items with history (some overdue, blocked, unassigned, closed with outcomes), and 6 knowledge docs (Cloud Hosting Standard, Incident SLA, Release runbook, SOW, Handover guidelines, Frontend notes). Dates are relative to *today* so overdue/upcoming states are always meaningful. Disable with `SEED_ON_START=false`.

## Logging

`app/logging_setup.py` – structlog → JSON lines, written to **`logs/app.log`** (rotating, 5 MB × 3) **and** stdout.

- **Levels**: INFO for business events, WARNING for 4xx, AI retries/fallbacks and detected conflicts, ERROR with stack trace for unhandled/DB errors.
- **Correlation ID**: middleware assigns `X-Request-ID` (or accepts the caller's), stores it in a contextvar so *every* log line in that request — including AI calls in worker threads — carries `request_id`. It's returned in the response header and in error bodies, and shown in UI error toasts.
- **Key events**: `meeting.created`, `meeting.status_changed`, `item.created`, `item.reassigned`, `item.status_changed`, `item.carried_forward`, `item.closed`, `item.reopened`, `recap.extracted`, `recap.applied`, `brief.generated`, `knowledge.linked`, `decision.conflict_detected`, `decision.conflict_resolved`, `http.request` (method, path, status, duration_ms).
- **AI calls**: `ai.call` with task, provider, model, attempt, outcome (`success|retry|error|disabled`), `latency_ms`, prompt/response **sizes** and token counts; `ai.fallback` with reason and total latency.
- **No secrets / minimal PII**: a redaction processor masks keys named like `api_key|token|secret|password|authorization` and values that look like API keys or bearer tokens. Prompt and response *content* is never logged.

Example:
```json
{"task":"extract_recap","provider":"gemini","model":"gemini-2.5-flash","attempt":1,"outcome":"success","latency_ms":1840,"prompt_chars":2211,"response_chars":903,"input_tokens":612,"output_tokens":240,"event":"ai.call","request_id":"7f3c9a1e2b4d4e10","level":"info","logger":"ai","timestamp":"2026-10-30T06:12:44.120Z"}
```

## Special feature: Decision Conflict Detector

**Problem it solves.** Losing context doesn't just mean forgetting tasks — it means teams *silently reverse earlier decisions or break their own policies* because the people in the room weren't there when the original call was made. In the seed data, the team agrees to host a client analytics dashboard on Azure, unaware that the Cloud Hosting Standard requires AWS ap-south-1 for banking clients (RBI data localisation). Nobody in that meeting would catch it.

**How it works.** Every time a decision is saved (manually or from a recap), the app retrieves the most related earlier decisions and knowledge-base documents, and asks the AI whether the new decision *contradicts, reverses or violates* any of them (refinements and agreements are explicitly not flagged). Conflicts are stored with severity, a plain-language explanation and a suggested resolution, then surfaced inline under the decision, on the meeting list, and on the dashboard. A human resolves each one as **intentional change** (with a note, e.g. "CTO approved by email") or **not a conflict** — so the decision trail stays honest.

**Why it adds value.** It turns the knowledge base from a passive archive into an active guard-rail, catches costly mistakes (compliance, rework) at the moment they're made, and creates an auditable record of *why* a past decision was overridden. Without AI it degrades to a conservative rule-based check (same topic + mutually exclusive terms like AWS/Azure).

### Second special feature: Follow-up Autopilot

The brief asks the app to *follow up on open items until they are closed*. Showing a list isn't following up, so the Follow-ups page (`/followups`, `services/followup.py`) does it:

1. **Slip-risk score 0–100** for every open item, from a transparent rule model: no owner +25, overdue +35 (+3/day, max +15), due ≤ 2 days and not started +15, each carry-forward +12 (max +30), blocked +20, high priority +10, owner has 4+ open items +10, open 14+ days +5; in progress −10, nudged in the last 2 days −15. Every score shows its reasons, so it can be explained to the person being chased.
2. **One-click AI nudge** per person: one message covering their riskiest items, friendly or firm, Slack or email (subject line, `mailto:` link to their address). Template fallback without AI.
3. **Closing the loop:** "Mark as sent" writes a `nudged` event into each item's history (`followup.nudge_sent` log), and a recent nudge lowers the score so nobody is chased twice in a row.

**Companion: "Going stale".** Items carried forward ≥2 times are highlighted on the dashboard with a carried-count badge — they're the ones that quietly die across meetings.

## Run locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add an AI key (optional)
uvicorn app.main:app --reload   # http://localhost:8000/docs

# Frontend (dev, hot reload; proxies /api to :8000)
cd frontend && npm install && npm run dev   # http://localhost:5173

# Or build the UI into backend/static and use only :8000
cd frontend && npm run build

# Tests (AI is mocked)
cd backend && pytest -q
```

## Deploy

**Render (recommended, free):** push to GitHub → Render → *New → Blueprint* → select the repo. `render.yaml` creates the Docker web service + a PostgreSQL database. Add `GEMINI_API_KEY` in the service's Environment tab.

**Any Docker host (Railway, Fly.io, a VM):**
```bash
docker build -t digiplus .
docker run -p 8000:8000 -e GEMINI_API_KEY=... -e DATABASE_URL=postgresql://... digiplus
```
The container reads `PORT` if the platform provides one. Logs go to `/app/logs/app.log` and stdout (so the platform's log viewer shows them too).

## Assumptions

- Single team / single tenant; no authentication (out of scope for the time box). People are identified by name.
- A "work transfer" is modelled as a meeting of kind `handover`, since it has the same shape.
- Meeting recordings are supported as **transcripts** (paste text); audio transcription is not included.
- Relative dates in notes ("by Friday") are resolved against the meeting date.

## Known limitations

- No auth/roles, no email/Slack notifications — reminders are surfaced in the dashboard only.
- Retrieval is keyword (BM25) based, not embeddings; synonyms with no shared words can be missed. The design allows swapping in embeddings in `retrieval.py`.
- AI calls are synchronous inside requests (bounded by timeout; conflict checks run in parallel threads). A job queue would be better at scale.
- Schema is created with `create_all` (no Alembic migrations yet).
- Rule-based fallbacks are intentionally conservative and work best with conventional note formats.
- On free hosting tiers the container may sleep; first request after idle is slow.
