"""Seed realistic DigiPlus data (only when the database is empty).

Dates are relative to today so overdue / upcoming states always look right in a demo.
Scenario: an IT services team delivering a client portal for "Northwind Bank" (fictional),
a work handover before someone's leave, and a small knowledge base of team policies.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .logging_setup import get_logger
from .models import (
    ActionItem, Decision, DecisionConflict, ItemHistory, KnowledgeDoc, KnowledgeLink, Meeting, Note, Participant,
)

log = get_logger("seed")

TEAM = {
    "Priya Sharma": ("priya.sharma@digiplus.example", "Delivery Manager"),
    "Rahul Mehta": ("rahul.mehta@digiplus.example", "Tech Lead"),
    "Sneha Iyer": ("sneha.iyer@digiplus.example", "Backend Engineer"),
    "Arjun Nair": ("arjun.nair@digiplus.example", "Frontend Engineer"),
    "Kavya Reddy": ("kavya.reddy@digiplus.example", "QA Lead"),
    "Vikram Singh": ("vikram.singh@digiplus.example", "DevOps Engineer"),
}

DOCS = [
    ("Cloud Hosting Standard", "policy", "cloud,aws,hosting,infrastructure,security",
     "All client production and staging workloads must run on AWS in the ap-south-1 (Mumbai) region to meet RBI data-localisation "
     "requirements for banking clients. Use of other cloud providers (Azure, GCP) for client data requires written approval from the "
     "CTO and the client's compliance officer. Infrastructure is provisioned with Terraform; manual console changes are not allowed "
     "in production. Owner: Vikram Singh (DevOps)."),
    ("Incident Escalation & SLA Policy", "policy", "incident,sla,escalation,support,p1",
     "Severity P1 (service down or data at risk): acknowledge within 15 minutes, client update every 30 minutes, resolution target 4 hours. "
     "P2 (major feature degraded): acknowledge within 1 hour, resolution target 1 business day. P3: next sprint. "
     "The on-call engineer owns the incident until handed over in writing. Post-incident review is mandatory for P1 within 3 business days."),
    ("Release & Code Review Runbook", "runbook", "release,deployment,code-review,qa,ci",
     "Every pull request needs one approving review and green CI (unit tests, lint, SAST scan). Releases to production happen on Tuesdays and "
     "Thursdays after QA sign-off from the QA Lead. Hotfixes may skip the release window but still need review. Feature flags are used for "
     "anything client-visible. Rollback plan must be written in the release ticket."),
    ("Northwind Bank Portal – Statement of Work (summary)", "spec", "northwind,sow,scope,portal,client",
     "Scope: customer self-service portal (account overview, statements download, card block/unblock), admin console, and integration with "
     "the bank's core banking API via their ESB. Out of scope: mobile apps, loan origination. Milestones: M1 login & account overview (done), "
     "M2 statements & card controls (due end of November), M3 admin console (January). Performance: p95 page load under 2 seconds. "
     "UAT environment is hosted by DigiPlus; production by the bank on AWS."),
    ("Leave & Work Handover Guidelines", "policy", "handover,leave,process,ownership",
     "Before planned leave longer than 3 days, the owner must create a handover listing: active tasks with status, open risks, key contacts, "
     "credentials location (never the credentials themselves), and pending decisions. The person taking over confirms receipt. "
     "Open action items are reassigned explicitly; nothing is left with an owner who is away."),
    ("Frontend Architecture Notes", "document", "frontend,react,architecture,performance,accessibility",
     "The portal frontend is React 18 + TypeScript with Vite. State via React Query; no Redux. Component library: internal DigiPlus UI kit. "
     "Accessibility target WCAG 2.1 AA. Statements PDF rendering is done server-side to keep bundle size small. "
     "Bundle budget: 250 KB gzipped for the initial route."),
]


def _dt(days: int, hour: int = 5) -> datetime:
    return datetime.combine(date.today() + timedelta(days=days), time(hour, 0), tzinfo=timezone.utc)


def _people(names, absent=()):
    return [Participant(name=n, email=TEAM[n][0], role=TEAM[n][1], attended=n not in absent) for n in names]


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Meeting.id).limit(1)):
        return
    docs = {}
    for title, dtype, tags, content in DOCS:
        d = KnowledgeDoc(title=title, doc_type=dtype, tags=tags, content=content)
        db.add(d)
        docs[title] = d
    db.flush()

    core = ["Priya Sharma", "Rahul Mehta", "Sneha Iyer", "Arjun Nair", "Kavya Reddy"]

    # ---------- Weekly sync #1 (3 weeks ago) ----------
    m1 = Meeting(
        title="Northwind Portal – Weekly Delivery Sync", scheduled_at=_dt(-21), status="completed", summary_source="ai",
        agenda="1. M1 retrospective\n2. Statements API approach\n3. UAT environment plan",
        summary="M1 (login and account overview) was accepted by the client. The team agreed to generate statement PDFs on the server "
                "and to host UAT on AWS ap-south-1. Main risk is slow responses from the bank's ESB sandbox.",
    )
    m1.participants = _people(core + ["Vikram Singh"])
    m1.notes = [Note(source="notes", author="Priya Sharma", content=(
        "M1 signed off by Northwind on Monday 🎉\nStatements: Rahul proposed server-side PDF generation, Arjun agreed (bundle size).\n"
        "Decision: statements PDFs generated server-side with WeasyPrint.\nDecision: UAT hosted on AWS ap-south-1 same as prod.\n"
        "ESB sandbox p95 is 3.8s — risk for the 2s budget.\nAction: Sneha to build statements API skeleton by next Wednesday\n"
        "Action: Vikram to provision UAT with Terraform\nAction: Kavya to write M2 test plan"))]
    db.add(m1)
    db.flush()
    db.add_all([
        Decision(meeting_id=m1.id, text="Statement PDFs are generated server-side (WeasyPrint), not in the browser.",
                 rationale="Keeps the frontend bundle under the 250 KB budget.", source="ai"),
        Decision(meeting_id=m1.id, text="UAT environment is hosted on AWS ap-south-1, mirroring production.",
                 rationale="Data-localisation rules and parity with the bank's prod setup.", source="ai"),
    ])

    # ---------- Weekly sync #2 (2 weeks ago) ----------
    m2 = Meeting(
        title="Northwind Portal – Weekly Delivery Sync", scheduled_at=_dt(-14), status="completed", previous_id=m1.id, summary_source="ai",
        agenda="1. Carried-over items\n2. ESB latency\n3. Card controls design",
        summary="Statements API skeleton is in review; UAT is up. ESB latency is still the main risk, so the team agreed to cache account "
                "summaries for 60 seconds. Arjun missed the meeting; card-controls UX review moved to next week.",
    )
    m2.participants = _people(core + ["Vikram Singh"], absent=["Arjun Nair"])
    m2.notes = [Note(source="transcript", author="auto-transcript", content=(
        "Priya: Let's go through last week's items. Sneha, statements API?\nSneha: Skeleton's up, PR in review, Rahul has it.\n"
        "Vikram: UAT is provisioned, all Terraform.\nRahul: ESB is still slow. I suggest we cache the account summary for 60 seconds.\n"
        "Priya: Agreed, let's do that. Card controls — Arjun's out today so we'll push the UX review.\n"
        "Kavya: Test plan draft is done but I need the card-block API contract.\nRahul: I'll share the contract by Friday."))]
    db.add(m2)
    db.flush()
    db.add(Decision(meeting_id=m2.id, text="Cache account summary responses for 60 seconds to work around ESB latency.",
                    rationale="ESB sandbox p95 is 3.8s; caching keeps the portal within the 2s budget.", source="ai"))

    # ---------- Weekly sync #3 (last week) ----------
    m3 = Meeting(
        title="Northwind Portal – Weekly Delivery Sync", scheduled_at=_dt(-7), status="completed", previous_id=m2.id, summary_source="ai",
        agenda="1. Carried-over items\n2. Card controls UX review\n3. Analytics dashboard request from client",
        summary="Card controls UX was approved with a confirmation step. The client asked for a usage analytics dashboard; Arjun proposed "
                "hosting it on Azure because the client's BI team uses Power BI, and the team agreed. Rahul starts two weeks of leave on "
                "Monday, so his work is being handed over to Sneha.",
    )
    m3.participants = _people(core)
    m3.notes = [Note(source="chat", author="Teams export", content=(
        "[11:02] Priya: card controls UX — looks good with the confirm dialog?\n[11:03] Kavya: yes, +1, covers the accidental-block case\n"
        "[11:10] Arjun: client wants an analytics dashboard. Their BI team is on Power BI so we could host it on Azure, easier for them\n"
        "[11:12] Priya: ok let's go with Azure for the analytics dashboard\n[11:15] Rahul: reminder I'm on leave from Monday for 2 weeks, "
        "handing over to Sneha\n[11:16] Sneha: 👍 will set up a handover session"))]
    db.add(m3)
    db.flush()
    d_azure = Decision(meeting_id=m3.id, text="Host the client usage analytics dashboard on Azure so it connects easily to the client's Power BI.",
                       rationale="Client BI team already uses Power BI.", source="ai")
    db.add_all([
        Decision(meeting_id=m3.id, text="Card block/unblock requires a confirmation step before the API call.",
                 rationale="Prevents accidental card blocks.", source="ai"),
        d_azure,
    ])

    # ---------- This week's sync (today, in progress) ----------
    m4 = Meeting(
        title="Northwind Portal – Weekly Delivery Sync", scheduled_at=_dt(0, 4), status="scheduled", previous_id=m3.id,
        agenda="1. Carried-over items\n2. M2 readiness (statements + card controls)\n3. Analytics dashboard hosting\n4. Rahul's handover check",
    )
    m4.participants = _people(["Priya Sharma", "Sneha Iyer", "Arjun Nair", "Kavya Reddy", "Vikram Singh"])
    db.add(m4)

    # ---------- Handover ----------
    h1 = Meeting(
        kind="handover", title="Handover: Rahul → Sneha (Northwind backend & ESB integration)", scheduled_at=_dt(-4, 4),
        status="completed", handover_from="Rahul Mehta", handover_to="Sneha Iyer", summary_source="ai",
        agenda="Active tasks, open risks, contacts, pending decisions",
        summary="Rahul handed over the statements API, the ESB integration and his open review queue to Sneha for two weeks. The ESB "
                "contact at Northwind is Mr. D'Souza; credentials are in the team vault. The card-block API contract is still outstanding.",
    )
    h1.participants = _people(["Rahul Mehta", "Sneha Iyer", "Priya Sharma"])
    h1.notes = [Note(source="email", author="Rahul Mehta", content=(
        "Subject: Handover before leave\n\nSneha — handing over:\n1) Statements API: PR #212 merged, pagination left (TODO Sneha by Friday)\n"
        "2) ESB: contact is D'Souza at Northwind IT; creds in vault under 'northwind-esb'. Cache is live.\n"
        "3) Card-block API contract: half done, doc in Confluence — please finish and send to Kavya\n4) Review queue: 3 PRs, mostly small.\n"
        "Risk: ESB rate limit is 50 rps in sandbox, prod unknown — ask D'Souza.\nThanks! Rahul"))]
    db.add(h1)

    # ---------- Standalone meeting ----------
    s1 = Meeting(
        title="Security review – Northwind M2", scheduled_at=_dt(-10, 9), status="completed", summary_source="manual",
        agenda="SAST findings, secrets handling, session timeout",
        summary="Two medium SAST findings in the statements service must be fixed before M2. Session timeout set to 10 minutes per bank policy.",
    )
    s1.participants = _people(["Rahul Mehta", "Vikram Singh", "Kavya Reddy"])
    db.add(s1)
    db.flush()
    db.add(Decision(meeting_id=s1.id, text="Portal session timeout is 10 minutes of inactivity.", rationale="Bank security policy.", source="manual"))

    # ---------- Action items with history ----------
    def item(origin, current, title, owner, due_days, status="open", priority="medium", outcome="", carried=0, closed_days=None,
             reassigned_from=None):
        it = ActionItem(title=title, owner=owner, due_date=date.today() + timedelta(days=due_days) if due_days is not None else None,
                        status=status, priority=priority, outcome=outcome, origin_meeting_id=origin.id, current_meeting_id=current.id,
                        times_carried=carried, source="ai", created_at=origin.scheduled_at,
                        closed_at=_dt(closed_days) if closed_days is not None else None)
        db.add(it)
        db.flush()
        db.add(ItemHistory(item_id=it.id, meeting_id=origin.id, event="created", to_value=title, note="Source: ai",
                           created_at=origin.scheduled_at))
        chain = [m1, m2, m3, m4]
        if origin in chain and current in chain:
            for a, b in zip(chain[chain.index(origin):chain.index(current)], chain[chain.index(origin) + 1:chain.index(current) + 1]):
                db.add(ItemHistory(item_id=it.id, meeting_id=b.id, event="carried_forward", from_value=a.title, to_value=b.title,
                                   note="Carried forward", created_at=b.scheduled_at))
        if reassigned_from:
            db.add(ItemHistory(item_id=it.id, meeting_id=h1.id, event="reassigned", from_value=reassigned_from, to_value=owner,
                               note="Reassigned during handover (Rahul on leave)", created_at=h1.scheduled_at))
        if status in ("done", "dropped"):
            db.add(ItemHistory(item_id=it.id, event="closed", from_value="in_progress", to_value=status, note=outcome,
                               meeting_id=current.id, created_at=_dt(closed_days or 0)))
        return it

    item(m1, m1, "Build statements API skeleton", "Sneha Iyer", -16, "done", outcome="PR #212 merged; endpoints for list and download.",
         closed_days=-12)
    item(m1, m1, "Provision UAT environment with Terraform", "Vikram Singh", -15, "done", outcome="UAT live at uat.northwind.digiplus.example",
         closed_days=-15)
    item(m1, m4, "Write M2 test plan (statements + card controls)", "Kavya Reddy", 3, "in_progress", carried=3)
    item(m2, m4, "Share card-block API contract with QA", "Sneha Iyer", -9, "open", "high", carried=2, reassigned_from="Rahul Mehta")
    item(m2, m3, "Card controls UX review with Arjun", "Arjun Nair", -8, "done", outcome="Approved with a confirmation dialog.", carried=1,
         closed_days=-7)
    item(m3, m4, "Set up analytics dashboard environment", "Arjun Nair", 5, "open", carried=1)
    item(m3, m4, "Get production ESB rate limits from Northwind IT", "", 2, "blocked", "high", carried=1)
    item(h1, h1, "Add pagination to statements API", "Sneha Iyer", -1, "in_progress", "medium", reassigned_from="Rahul Mehta")
    item(h1, h1, "Clear Rahul's PR review queue (3 PRs)", "Sneha Iyer", 1, "open", "low", reassigned_from="Rahul Mehta")
    item(s1, s1, "Fix 2 medium SAST findings in statements service", "Sneha Iyer", 4, "open", "high")
    item(s1, s1, "Document session-timeout config in runbook", "Vikram Singh", -3, "done", outcome="Runbook updated, section 4.2.",
         closed_days=-3)
    db.flush()

    # ---------- Pre-computed knowledge links + one conflict (so the demo shows the features without an API key) ----------
    db.add_all([
        KnowledgeLink(meeting_id=m3.id, doc_id=docs["Cloud Hosting Standard"].id, score=0.92, source="ai",
                      reason="The Azure hosting decision falls under this standard, which requires AWS ap-south-1 for client data."),
        KnowledgeLink(meeting_id=m3.id, doc_id=docs["Leave & Work Handover Guidelines"].id, score=0.7, source="ai",
                      reason="Rahul's upcoming leave triggers the handover process defined here."),
        KnowledgeLink(meeting_id=h1.id, doc_id=docs["Leave & Work Handover Guidelines"].id, score=0.9, source="ai",
                      reason="Defines what this handover must contain and that open items must be explicitly reassigned."),
        KnowledgeLink(meeting_id=m2.id, doc_id=docs["Northwind Bank Portal – Statement of Work (summary)"].id, score=0.8, source="ai",
                      reason="The SOW sets the p95 < 2s target that the caching decision is protecting."),
        KnowledgeLink(meeting_id=m4.id, linked_meeting_id=m3.id, score=0.85, source="ai",
                      reason="Last week's sync recorded the analytics hosting decision on today's agenda."),
    ])
    db.add(DecisionConflict(
        decision_id=d_azure.id, meeting_id=m3.id, conflicting_doc_id=docs["Cloud Hosting Standard"].id, severity="high",
        explanation="Hosting a client analytics dashboard on Azure conflicts with the Cloud Hosting Standard, which requires client "
                    "workloads on AWS ap-south-1 and written CTO + client compliance approval for any other provider.",
        suggestion="Either get written approval from the CTO and Northwind's compliance officer, or host on AWS and connect Power BI via a gateway.",
    ))
    db.commit()
    log.info("seed.completed", meetings=6, docs=len(DOCS))
