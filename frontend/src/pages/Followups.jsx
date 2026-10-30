import { useState } from "react";
import { Link } from "react-router-dom";
import { BellRing, Check, Copy, Mail, MessageSquare, Send, ShieldCheck, Sparkles, UserX } from "lucide-react";
import { api, fmtDate, fmtDateTime } from "../api";
import { AIBanner, Empty, PageLoader, Spinner, useAction, useLoad } from "../components/ui";
import { CountUp } from "../components/Effects";

const LEVEL = {
  high: { ring: "stroke-red-500", text: "text-red-600", chip: "bg-red-50 text-red-700", label: "High risk" },
  medium: { ring: "stroke-amber-500", text: "text-amber-600", chip: "bg-amber-50 text-amber-700", label: "Medium" },
  low: { ring: "stroke-emerald-500", text: "text-emerald-600", chip: "bg-emerald-50 text-emerald-700", label: "Low" },
};
const initials = (n) => n.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();

// Circular 0-100 gauge for one item's slip risk.
function RiskRing({ score, level }) {
  const r = 16, c = 2 * Math.PI * r;
  return (
    <div className="relative w-11 h-11 shrink-0" title={`Slip risk ${score}/100`}>
      <svg viewBox="0 0 40 40" className="w-11 h-11 -rotate-90">
        <circle cx="20" cy="20" r={r} className="stroke-slate-100" strokeWidth="4" fill="none" />
        <circle cx="20" cy="20" r={r} className={`${LEVEL[level].ring} transition-all duration-700`} strokeWidth="4" fill="none"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - score / 100)} />
      </svg>
      <span className={`absolute inset-0 grid place-items-center text-[11px] font-semibold ${LEVEL[level].text}`}>{score}</span>
    </div>
  );
}

function NudgeComposer({ owner, onSent }) {
  const [tone, setTone] = useState("friendly");
  const [channel, setChannel] = useState("slack");
  const [draft, setDraft] = useState(null);
  const [copied, setCopied] = useState(false);
  const [run, busy] = useAction();

  const generate = async () => {
    const r = await run(() => api.post("/followups/draft", { owner: owner.owner, tone, channel }));
    if (r) setDraft(r);
  };
  const copy = async () => {
    const text = draft.subject ? `Subject: ${draft.subject}\n\n${draft.message}` : draft.message;
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  const markSent = async () => {
    const r = await run(() => api.post("/followups/sent", { owner: owner.owner, item_ids: draft.item_ids, channel }), `Follow-up to ${owner.owner.split(" ")[0]} logged in item history`);
    if (r) { setDraft(null); onSent(); }
  };
  const mailto = draft && `mailto:${encodeURIComponent(draft.email || "")}?subject=${encodeURIComponent(draft.subject || "Follow-up")}&body=${encodeURIComponent(draft.message)}`;

  const Toggle = ({ value, set, options }) => (
    <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
      {options.map(([v, label, Icon]) => (
        <button key={v} type="button" onClick={() => { set(v); setDraft(null); }}
          className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded-md transition ${value === v ? "bg-white shadow-sm text-slate-900 font-medium" : "text-slate-500"}`}>
          {Icon && <Icon className="w-3.5 h-3.5" />}{label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="border-t border-slate-100 bg-slate-50/60 px-5 py-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Toggle value={tone} set={setTone} options={[["friendly", "Friendly"], ["firm", "Firm"]]} />
        <Toggle value={channel} set={setChannel} options={[["slack", "Slack", MessageSquare], ["email", "Email", Mail]]} />
        <button className="btn-primary ml-auto" onClick={generate} disabled={busy}>{busy && !draft ? <Spinner /> : <Sparkles className="w-4 h-4" />}{draft ? "Regenerate" : "Draft nudge"}</button>
      </div>
      {draft && (
        <div className="space-y-2 animate-pop">
          <AIBanner status={draft.ai_status} message={draft.ai_message} />
          {draft.subject !== "" && channel === "email" && (
            <input className="input font-medium" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
          )}
          <textarea className="input min-h-36 leading-relaxed" value={draft.message} onChange={(e) => setDraft({ ...draft, message: e.target.value })} />
          <div className="flex flex-wrap gap-2 justify-end">
            <button className="btn-secondary" onClick={copy}>{copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}{copied ? "Copied" : "Copy"}</button>
            {channel === "email" && <a className="btn-secondary" href={mailto}><Mail className="w-4 h-4" />Open in email</a>}
            <button className="btn-solid" onClick={markSent} disabled={busy}><Send className="w-4 h-4" />Mark as sent</button>
          </div>
        </div>
      )}
    </div>
  );
}

function OwnerCard({ o, onSent }) {
  const [open, setOpen] = useState(false);
  const unassigned = !o.owner;
  return (
    <section className={`card overflow-hidden card-hover ${o.high ? "ring-1 ring-red-100" : ""}`}>
      <header className="flex items-center gap-3 px-5 py-4">
        {unassigned ? (
          <span className="w-10 h-10 rounded-full bg-red-50 text-red-500 grid place-items-center"><UserX className="w-5 h-5" /></span>
        ) : (
          <span className="w-10 h-10 rounded-full bg-brand-gradient text-white grid place-items-center text-sm font-semibold">{initials(o.owner)}</span>
        )}
        <div className="min-w-0">
          <div className="font-semibold text-slate-900">{unassigned ? "Unassigned" : o.owner}</div>
          <div className="text-xs text-slate-500">
            {o.items.length} open{o.high ? <span className="text-red-600"> · {o.high} high risk</span> : null}{o.medium ? <span className="text-amber-600"> · {o.medium} medium</span> : null}
            {o.email && <span className="hidden sm:inline"> · {o.email}</span>}
          </div>
        </div>
        {!unassigned ? (
          <button className={open ? "btn-secondary ml-auto" : "btn-primary ml-auto"} onClick={() => setOpen(!open)}>
            <BellRing className="w-4 h-4" />{open ? "Close" : "Nudge"}
          </button>
        ) : (
          <span className="ml-auto text-xs text-red-600 font-medium">Assign an owner first</span>
        )}
      </header>
      <ul className="divide-y divide-slate-100 border-t border-slate-100">
        {o.items.map((i) => (
          <li key={i.id} className="flex gap-3 px-5 py-3">
            <RiskRing score={i.score} level={i.level} />
            <div className="min-w-0 flex-1">
              <Link to={`/meetings/${i.meeting_id}`} className="text-sm font-medium hover:text-brand-600">{i.title}</Link>
              <div className="flex flex-wrap gap-1 mt-1">
                {i.reasons.map((r) => <span key={r} className={`chip ${r.includes("−") ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{r}</span>)}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Due {fmtDate(i.due_date)} · {i.meeting_title}{i.last_nudged ? ` · last nudged ${fmtDateTime(i.last_nudged)}` : ""}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {open && <NudgeComposer owner={o} onSent={() => { setOpen(false); onSent(); }} />}
    </section>
  );
}

export default function Followups() {
  const state = useLoad(() => api.get("/followups"));
  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="eyebrow mb-2"><span className="w-6 h-px bg-brand-600" />Follow-up autopilot</div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Who needs a <span className="text-gradient">nudge</span> today</h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">Every open item gets a 0–100 slip-risk score with the reasons behind it. Draft a personalised follow-up in one click, send it, and it's logged in the item's history.</p>
        </div>
      </div>
      <PageLoader state={state}>
        {(d) => (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[["Open items", d.summary.open, "text-slate-900"], ["High risk", d.summary.high, "text-red-600"], ["Medium risk", d.summary.medium, "text-amber-600"], ["People to nudge", d.summary.owners_to_nudge, "text-brand-600"]].map(([label, v, tone]) => (
                <div key={label} className="card px-4 py-3.5">
                  <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</div>
                  <div className={`text-3xl font-semibold mt-1 tabular-nums ${tone}`}><CountUp value={v} /></div>
                </div>
              ))}
            </div>
            <details className="card px-5 py-3 text-sm text-slate-600 group">
              <summary className="cursor-pointer font-medium text-slate-800 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-brand-600" />How the risk score works</summary>
              <p className="mt-2 text-xs leading-relaxed">Points are added for: no owner (+25), overdue (+35, +3 per day up to +15 more), due within 2 days and not started (+15), each carry-forward (+12, max +30), blocked (+20), high priority (+10), owner has 4+ open items (+10), open more than 14 days (+5). Points are removed for: in progress (−10), nudged in the last 2 days (−15). High ≥ 60, medium ≥ 35. The model is deliberately transparent so every number can be explained to the person being chased.</p>
            </details>
            <div className="grid lg:grid-cols-2 gap-4 items-start">
              {d.owners.map((o) => <OwnerCard key={o.owner || "__none"} o={o} onSent={state.reload} />)}
            </div>
            {!d.owners.length && <div className="card"><Empty title="No open items" hint="Nothing to chase. Nice." /></div>}
          </>
        )}
      </PageLoader>
    </div>
  );
}
