"""End-to-end API tests. AI is mocked so tests are fast, free and deterministic.

Run:  cd backend && pytest -q
"""
import json
import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["LOG_FILE"] = f"{tempfile.mkdtemp()}/test.log"
os.environ["SEED_ON_START"] = "true"
os.environ["AI_PROVIDER"] = "none"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ai_client  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_ai(monkeypatch):
    """Route AI calls to a fake provider that returns whatever the test queues up."""
    responses = []

    def fake(system, user, http_client):
        if not responses:
            raise ai_client.httpx.ConnectError("no response queued")
        r = responses.pop(0)
        return (r if isinstance(r, str) else json.dumps(r)), {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setitem(ai_client.PROVIDERS, "fake", fake)
    monkeypatch.setitem(ai_client.MODELS, "fake", lambda: "fake-model")
    monkeypatch.setattr(settings, "ai_provider", "fake")
    monkeypatch.setattr(settings, "ai_max_retries", 1)
    monkeypatch.setattr(ai_client.time, "sleep", lambda s: None)
    return responses


def new_meeting(client, **kw):
    body = {"title": "Test sync", "scheduled_at": "2026-10-30T05:00:00Z", "participants": [{"name": "Asha Rao"}, {"name": "Dev Patel"}]}
    body.update(kw)
    r = client.post("/api/meetings", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_seed(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/meetings").json()) >= 6
    assert client.get("/api/dashboard").json()["counts"]["open_conflicts"] >= 1


def test_request_id_header_and_validation_error(client):
    r = client.post("/api/meetings", json={"title": "  ", "scheduled_at": "nope"})
    assert r.status_code == 422
    body = r.json()
    assert body["request_id"] == r.headers["X-Request-ID"]
    assert {d["field"] for d in body["details"]} == {"title", "scheduled_at"}


def test_caller_request_id_is_propagated(client):
    r = client.get("/api/health", headers={"X-Request-ID": "trace-abc123"})
    assert r.headers["X-Request-ID"] == "trace-abc123"


def test_lifecycle_rules(client):
    m = new_meeting(client)
    assert client.post(f"/api/meetings/{m['id']}/status", json={"status": "completed"}).status_code == 200
    r = client.post(f"/api/meetings/{m['id']}/status", json={"status": "cancelled"})
    assert r.status_code == 409


def test_item_reassign_close_and_history(client):
    m = new_meeting(client)
    item = client.post(f"/api/meetings/{m['id']}/items", json={"title": "Write docs", "owner": "Asha Rao"}).json()
    client.patch(f"/api/items/{item['id']}", json={"owner": "Dev Patel", "note": "Asha on leave"})
    assert client.post(f"/api/items/{item['id']}/close", json={"outcome": "no"}).status_code == 422  # outcome too short
    closed = client.post(f"/api/items/{item['id']}/close", json={"outcome": "Docs published to wiki"}).json()
    assert closed["status"] == "done" and closed["outcome"] == "Docs published to wiki"
    assert [h["event"] for h in closed["history"]] == ["created", "reassigned", "closed"]
    assert client.post(f"/api/items/{item['id']}/close", json={"outcome": "again please"}).status_code == 409


def test_carry_forward_keeps_history(client):
    m1 = new_meeting(client)
    open_item = client.post(f"/api/meetings/{m1['id']}/items", json={"title": "Open thing"}).json()
    done_item = client.post(f"/api/meetings/{m1['id']}/items", json={"title": "Done thing"}).json()
    client.post(f"/api/items/{done_item['id']}/close", json={"outcome": "Finished it"})

    m2 = client.post(f"/api/meetings/{m1['id']}/follow-up", json={"title": "Test sync 2", "scheduled_at": "2026-11-06T05:00:00Z"}).json()
    ids = {i["id"] for i in m2["items"]}
    assert open_item["id"] in ids and done_item["id"] not in ids
    detail = client.get(f"/api/items/{open_item['id']}").json()
    assert detail["times_carried"] == 1 and detail["origin_meeting_id"] == m1["id"]
    assert detail["history"][-1]["event"] == "carried_forward"


def test_extract_without_ai_uses_fallback(client):
    m = new_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/extract", json={"raw_text": "Decision: ship on Tuesday\nAction: Dev to fix login bug by Friday"})
    body = r.json()
    assert body["ai_status"] == "disabled"
    assert body["decisions"][0]["text"].startswith("ship on Tuesday")
    assert body["action_items"][0]["owner"] == "Dev Patel"


def test_extract_with_ai(client, fake_ai):
    fake_ai.append({
        "summary": "Agreed to ship.",
        "decisions": [{"text": "Ship on Tuesday", "rationale": "QA done"}],
        "action_items": [{"title": "Fix login bug", "owner": "Dev Patel", "due_date": "2026-11-03", "priority": "high"}],
        "open_questions": [],
    })
    m = new_meeting(client)
    body = client.post(f"/api/meetings/{m['id']}/extract", json={"raw_text": "some messy notes here"}).json()
    assert body["ai_status"] == "ok" and body["action_items"][0]["priority"] == "high"


def test_ai_bad_json_retries_then_falls_back(client, fake_ai):
    fake_ai.extend(["not json at all", '{"wrong": "shape"}'])
    m = new_meeting(client)
    body = client.post(f"/api/meetings/{m['id']}/extract", json={"raw_text": "Action: Asha to call client"}).json()
    assert body["ai_status"] == "fallback"
    assert body["action_items"][0]["owner"] == "Asha Rao"


def test_ai_json_in_code_fence_is_accepted(client, fake_ai):
    fake_ai.append('Here you go:\n```json\n{"brief": "**TL;DR** – all good"}\n```')
    m = new_meeting(client)
    r = client.get(f"/api/meetings/{m['id']}/brief", params={"person": "Dev Patel"}).json()
    assert r["ai_status"] == "ok" and "TL;DR" in r["brief"]


def test_conflict_detection_flags_contradiction(client, fake_ai):
    # Conflict detector should compare the new decision with the seeded Cloud Hosting Standard.
    def respond(system, user, http_client):
        import re
        key = re.search(r"\[(doc:\d+)\]", user).group(1)
        return json.dumps({"conflicts": [{"candidate_key": key, "severity": "high", "explanation": "Policy says AWS.", "suggestion": "Get CTO approval."}]}), {}

    ai_client.PROVIDERS["fake"] = respond
    m = new_meeting(client)
    detail = client.post(f"/api/meetings/{m['id']}/decisions", json={"text": "Host client staging on GCP to save cost"}).json()
    assert len(detail["conflicts"]) == 1 and detail["conflicts"][0]["severity"] == "high"
    cid = detail["conflicts"][0]["id"]
    assert client.post(f"/api/conflicts/{cid}/resolve", json={"status": "accepted", "resolution_note": "CTO ok"}).json()["status"] == "accepted"


def test_ai_hallucinated_reference_is_ignored(client, fake_ai):
    fake_ai.append({"links": [{"candidate_key": "doc:99999", "item_id": None, "reason": "made up", "score": 0.9}]})
    m = new_meeting(client, agenda="AWS hosting standard review")
    r = client.post(f"/api/meetings/{m['id']}/link-knowledge").json()
    assert all(l["doc_id"] != 99999 for l in r["links"])


def test_logs_are_json_with_request_id_and_no_secrets(client, monkeypatch):
    from app.logging_setup import get_logger

    get_logger("test").info("secret.test", api_key="sk-abcdefghijklmnop", detail="token AIzaSyA1234567890abcdefghijk")
    client.get("/api/health", headers={"X-Request-ID": "logcheck1"})
    lines = [json.loads(l) for l in open(settings.log_file, encoding="utf-8") if l.strip()]
    assert any(l.get("request_id") == "logcheck1" and l["event"] == "http.request" for l in lines)
    secret_line = next(l for l in lines if l["event"] == "secret.test")
    assert secret_line["api_key"] == "[REDACTED]" and "AIza" not in secret_line["detail"]


def test_followup_risk_scoring_and_nudge_trail(client):
    board = client.get("/api/followups").json()
    scores = [i["score"] for o in board["owners"] for i in o["items"]]
    assert board["summary"]["open"] == len(scores) and board["summary"]["high"] >= 1
    top = board["owners"][0]["items"][0]
    assert top["level"] == "high" and top["reasons"]  # every score is explained

    owner = next(o for o in board["owners"] if o["owner"])
    draft = client.post("/api/followups/draft", json={"owner": owner["owner"], "tone": "firm", "channel": "email"}).json()
    assert draft["ai_status"] == "disabled" and owner["owner"].split()[0] in draft["message"] and draft["subject"]

    sent = client.post("/api/followups/sent", json={"owner": owner["owner"], "item_ids": draft["item_ids"], "channel": "email"}).json()
    assert sent["recorded"] == len(draft["item_ids"])
    history = client.get(f"/api/items/{draft['item_ids'][0]}").json()["history"]
    assert history[-1]["event"] == "nudged"
    # a fresh nudge lowers the score so the same person isn't chased twice in a row
    after = next(i for o in client.get("/api/followups").json()["owners"] for i in o["items"] if i["id"] == draft["item_ids"][0])
    assert "nudged recently (−15)" in after["reasons"]


def test_followup_validation(client):
    assert client.post("/api/followups/draft", json={"owner": "Nobody Here"}).status_code == 404
    assert client.post("/api/followups/draft", json={"owner": "x", "tone": "angry"}).status_code == 422


def test_gemini_falls_back_to_next_model_on_404(monkeypatch):
    """A retired model (404) should not break AI: the client moves on to the next model."""
    import httpx
    from app.services import ai_client

    seen = []

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        seen.append(model)
        if model == "retired-model":
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"brief": "ok"}'}]}}], "usageMetadata": {}})

    real_client = httpx.Client
    monkeypatch.setattr(ai_client.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-test")
    monkeypatch.setattr(settings, "gemini_model", "retired-model")
    monkeypatch.setattr(settings, "gemini_fallback_models", ["good-model"])
    monkeypatch.setattr(ai_client, "_working_gemini_model", None)

    result = ai_client.call_json("test", "system", "user")
    assert result.status == "ok" and result.data == {"brief": "ok"}
    assert seen == ["retired-model", "good-model"]
    assert ai_client.provider_info()["model"] == "good-model"


def test_gemini_overloaded_503_moves_to_another_model(monkeypatch):
    import httpx
    from app.services import ai_client

    seen = []

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        seen.append(model)
        if model == "busy-model":
            return httpx.Response(503, json={"error": {"message": "The model is overloaded"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"brief": "ok"}'}]}}]})

    real_client = httpx.Client
    monkeypatch.setattr(ai_client.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-test")
    monkeypatch.setattr(settings, "gemini_model", "busy-model")
    monkeypatch.setattr(settings, "gemini_fallback_models", ["calm-model"])
    monkeypatch.setattr(ai_client, "_working_gemini_model", None)
    assert ai_client.call_json("test", "s", "u").status == "ok"
    assert seen == ["busy-model", "calm-model"]


def test_fallback_reads_a_pasted_paragraph():
    from datetime import datetime
    from app.services.intelligence import fallback_extract

    text = ("Quick update from today's meeting. We need to finish the dashboard by Friday. "
            "Riya will handle the frontend UI. Decision: ship the beta on Monday. Who owns the API docs?")
    r = fallback_extract(text, datetime(2026, 10, 28), [])
    assert [d.text for d in r["decisions"]] == ["ship the beta on Monday."]
    titles = {i.title: i for i in r["action_items"]}
    assert titles["Finish the dashboard by Friday"].due_date.isoformat() == "2026-10-30"
    assert titles["Riya will handle the frontend UI"].owner == "Riya"
    assert r["open_questions"] == ["Who owns the API docs?"]


# ---------------------------------------------------------------- uploads
def _pdf_bytes(lines):
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


def _docx_bytes(paragraphs):
    import io
    import zipfile
    from xml.sax.saxutils import escape

    body = "".join(f"<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


SAMPLE_VTT = """WEBVTT

a1/1-0
00:00:01.000 --> 00:00:04.000
<v Asha Rao>Decision: we release on Thursday after QA sign-off.</v>

a1/2-0
00:00:04.500 --> 00:00:08.000
<v Dev Patel>I will fix the login bug by Friday.</v>

a1/3-0
00:00:08.500 --> 00:00:10.000
<v Dev Patel>It's urgent for the client.</v>

a1/4-0
00:00:10.500 --> 00:00:13.000
<v Meera Iyer>Action: Meera to update the release notes tomorrow</v>
"""


def test_upload_pdf_suggests_title_type_and_tags(client):
    pdf = _pdf_bytes(["Data Retention Policy", "All client logs must be deleted after 90 days.",
                      "Backups must be encrypted. Retention policy compliance is required for every banking client."])
    r = client.post("/api/knowledge/analyze", files={"file": ("data_retention.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "pdf" and d["pages"] == 1 and "90 days" in d["content"]
    assert d["title"] == "Data Retention Policy" and d["doc_type"] == "policy" and d["tags"]
    assert d["ai_status"] == "disabled"


def test_upload_rejects_bad_files(client):
    assert client.post("/api/knowledge/analyze", files={"file": ("virus.exe", b"MZ...", "application/octet-stream")}).status_code == 422
    assert client.post("/api/knowledge/analyze", files={"file": ("empty.txt", b"", "text/plain")}).status_code == 422
    assert client.post("/api/knowledge/analyze", files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")}).status_code == 422


def test_teams_vtt_transcript_creates_recap_and_adds_speakers(client):
    m = new_meeting(client, participants=[{"name": "Asha Rao"}])
    r = client.post(f"/api/meetings/{m['id']}/transcript", files={"file": ("Sync.vtt", SAMPLE_VTT.encode(), "text/vtt")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["speakers"] == ["Asha Rao", "Dev Patel", "Meera Iyer"]
    assert d["speakers_added"] == ["Dev Patel", "Meera Iyer"]
    assert any("Thursday" in x["text"] for x in d["decisions"])
    owners = {i["owner"] for i in d["action_items"]}
    assert "Meera Iyer" in owners
    detail = client.get(f"/api/meetings/{m['id']}").json()
    assert detail["notes"][-1]["source"] == "transcript" and "Dev Patel: I will fix the login bug" in detail["notes"][-1]["content"]


def test_teams_docx_transcript_format(client):
    m = new_meeting(client)
    docx = _docx_bytes(["Weekly sync transcript", "Asha Rao   0:03", "Decision: move the demo to Monday.",
                        "Dev Patel   0:15", "Action: Dev to prepare the demo data"])
    d = client.post(f"/api/meetings/{m['id']}/transcript",
                    files={"file": ("sync.docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}).json()
    assert d["speakers"] == ["Asha Rao", "Dev Patel"]
    assert d["decisions"] and d["action_items"][0]["owner"] == "Dev Patel"
