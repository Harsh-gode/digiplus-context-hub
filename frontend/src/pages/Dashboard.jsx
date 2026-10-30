import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, CalendarClock, Columns3, CornerDownRight, MessageCircleQuestion, Plus, ShieldAlert, Sparkles } from "lucide-react";
import { api, fmtDateTime } from "../api";
import { Empty, KindBadge, PageLoader, SeverityBadge, StatusBadge, useLoad } from "../components/ui";
import { CountUp, ParticleField } from "../components/Effects";
import ItemDrawer from "../components/ItemDrawer";
import ItemTable from "../components/ItemTable";
import NewMeetingModal from "../components/NewMeetingModal";

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

// KPI tile in the style of the DigiPlus "Intelligence Dashboard" mockup.
function Stat({ label, value, sub, tone = "slate", to }) {
  const subTone = { slate: "text-slate-400", red: "text-red-500", amber: "text-amber-600", emerald: "text-emerald-600", violet: "text-brand-600" };
  const body = (
    <div className="card card-hover px-4 py-3.5 h-full">
      <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</div>
      <div className="text-3xl font-semibold text-slate-900 mt-1 tabular-nums"><CountUp value={value} /></div>
      <div className={`text-xs mt-0.5 ${subTone[tone]}`}>{sub}</div>
    </div>
  );
  return to ? <Link to={to} className="block">{body}</Link> : body;
}

function Hero({ d }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const c = d.counts;
  return (
    <section className="relative overflow-hidden card px-6 md:px-10 py-10 md:py-12">
      <ParticleField />
      <div className="relative max-w-2xl animate-fade-up">
        <div className="eyebrow"><span className="w-6 h-px bg-brand-600" />{greeting()} · Team intelligence</div>
        <h1 className="mt-3 text-3xl md:text-5xl font-semibold tracking-tight text-slate-950 leading-[1.08]">
          Nothing slips between <span className="text-gradient">meetings.</span>
        </h1>
        <p className="mt-4 text-slate-500 text-[15px] leading-relaxed">
          {c.open} open items across {c.meetings} meetings and handovers
          {c.overdue ? <> — <span className="text-red-600 font-medium">{c.overdue} overdue</span></> : null}
          {c.open_conflicts ? <>, and <span className="text-brand-600 font-medium">{c.open_conflicts} decision {c.open_conflicts === 1 ? "conflict" : "conflicts"}</span> to review</> : null}.
        </p>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) nav(`/ask?q=${encodeURIComponent(q.trim())}`); }}
          className="mt-6 flex items-center gap-2 bg-white rounded-2xl border border-slate-200 shadow-sm p-1.5 pl-4 focus-within:ring-4 focus-within:ring-brand-100 focus-within:border-brand-300 transition">
          <MessageCircleQuestion className="w-4 h-4 text-slate-400 shrink-0" />
          <input value={q} onChange={(e) => setQ(e.target.value)} className="flex-1 text-sm outline-none bg-transparent py-1.5"
            placeholder="Ask the team memory — e.g. “What did Rahul hand over?”" />
          <button className="btn-primary" disabled={q.trim().length < 3}><Sparkles className="w-4 h-4" />Ask</button>
        </form>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={() => setNewOpen(true)}><Plus className="w-4 h-4" />New meeting or handover</button>
          <Link to="/items" className="btn-secondary"><Columns3 className="w-4 h-4" />Open the board<ArrowRight className="w-3.5 h-3.5" /></Link>
        </div>
      </div>
      <NewMeetingModal open={newOpen} onClose={() => setNewOpen(false)} people={[]} />
    </section>
  );
}

export default function Dashboard() {
  const state = useLoad(() => Promise.all([api.get("/dashboard"), api.get("/conflicts?status=open"), api.get("/people")]));
  const [openItem, setOpenItem] = useState(null);

  return (
    <PageLoader state={state}>
      {([d, conflicts, people]) => (
        <div className="space-y-6">
          <Hero d={d} />

          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 animate-fade-up" style={{ animationDelay: "80ms" }}>
            <Stat label="Open items" value={d.counts.open} sub="across all meetings" to="/items" />
            <Stat label="Overdue" value={d.counts.overdue} sub={d.counts.overdue ? "↑ needs follow-up" : "all on track"} tone={d.counts.overdue ? "red" : "emerald"} to="/items?layout=list&view=overdue" />
            <Stat label="Blocked" value={d.counts.blocked} sub={d.counts.blocked ? "waiting on someone" : "nothing blocked"} tone={d.counts.blocked ? "amber" : "emerald"} to="/items?layout=list&view=blocked" />
            <Stat label="Unassigned" value={d.counts.unassigned} sub={d.counts.unassigned ? "needs an owner" : "everyone has one"} tone={d.counts.unassigned ? "amber" : "emerald"} to="/items?layout=list&view=open&owner=" />
            <Stat label="Closed · 7 days" value={d.counts.closed_this_week} sub="↑ outcomes recorded" tone="emerald" to="/items?layout=list&view=closed" />
            <Stat label="Conflicts" value={d.counts.open_conflicts} sub={d.counts.open_conflicts ? "decisions to review" : "decision trail clean"} tone={d.counts.open_conflicts ? "violet" : "emerald"} />
          </div>

          {conflicts.length > 0 && (
            <div className="card overflow-hidden animate-fade-up" style={{ animationDelay: "140ms" }}>
              <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
                <div className="section-title"><ShieldAlert className="w-4 h-4 text-brand-600" />Decisions that contradict earlier decisions or policy</div>
                <span className="chip bg-brand-gradient text-white">AI guard-rail</span>
              </div>
              <div className="divide-y divide-slate-100">
                {conflicts.slice(0, 4).map((c) => (
                  <Link key={c.id} to={`/meetings/${c.meeting_id}#conflicts`} className="block px-5 py-3.5 hover:bg-brand-50/40 transition group">
                    <div className="flex items-center gap-2 mb-1"><SeverityBadge severity={c.severity} /><span className="text-sm font-medium">{c.decision_text}</span>
                      <ArrowRight className="w-3.5 h-3.5 ml-auto text-slate-300 group-hover:text-brand-600 group-hover:translate-x-0.5 transition" /></div>
                    <div className="text-xs text-slate-500">vs. <span className="font-medium text-slate-600">{c.conflicting_source_title}</span> — {c.explanation}</div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="grid lg:grid-cols-3 gap-6 animate-fade-up" style={{ animationDelay: "200ms" }}>
            <div className="lg:col-span-2 space-y-6">
              <div className="card overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100 section-title"><CalendarClock className="w-4 h-4 text-red-500" />Overdue</div>
                {d.overdue.length ? <ItemTable items={d.overdue} onOpen={setOpenItem} /> : <Empty title="Nothing overdue" hint="Nice." />}
              </div>
              <div className="card overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100">
                  <div className="section-title"><CornerDownRight className="w-4 h-4 text-orange-500" />Going stale</div>
                  <div className="text-xs text-slate-500 mt-0.5">Carried forward 2+ times without closing — these are the items that quietly die.</div>
                </div>
                {d.stale.length ? <ItemTable items={d.stale} onOpen={setOpenItem} /> : <Empty title="No stale items" />}
              </div>
            </div>
            <div className="space-y-6">
              <div className="card overflow-hidden">
                <div className="px-5 py-3.5 border-b border-slate-100 section-title">Upcoming</div>
                {d.upcoming.length ? (
                  <div className="divide-y divide-slate-100">
                    {d.upcoming.map((m) => (
                      <Link key={m.id} to={`/meetings/${m.id}`} className="block px-5 py-3 hover:bg-brand-50/40 transition">
                        <div className="text-sm font-medium">{m.title}</div>
                        <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                          <KindBadge kind={m.kind} /><StatusBadge status={m.status} />{fmtDateTime(m.scheduled_at)}
                        </div>
                        {m.open_item_count > 0 && <div className="text-xs text-orange-600 mt-1">{m.open_item_count} open items on the agenda</div>}
                      </Link>
                    ))}
                  </div>
                ) : <Empty title="Nothing scheduled" />}
              </div>
              <div className="card">
                <div className="px-5 py-3.5 border-b border-slate-100 section-title">Open items by owner</div>
                <div className="p-5 space-y-3">
                  {d.by_owner.map((o) => {
                    const max = Math.max(...d.by_owner.map((x) => x.open));
                    return (
                      <Link key={o.owner} to={`/items?owner=${encodeURIComponent(o.owner === "Unassigned" ? "" : o.owner)}`} className="block group">
                        <div className="flex justify-between text-xs mb-1">
                          <span className={`font-medium group-hover:text-brand-600 ${o.owner === "Unassigned" ? "text-red-600" : ""}`}>{o.owner}</span>
                          <span className="text-slate-500">{o.open} open{o.overdue ? <span className="text-red-600"> · {o.overdue} overdue</span> : null}</span>
                        </div>
                        <div className="h-2 rounded-full bg-slate-100 overflow-hidden flex">
                          <div className="bg-red-500 transition-all duration-700" style={{ width: `${(o.overdue / max) * 100}%` }} />
                          <div className="bg-brand-gradient transition-all duration-700" style={{ width: `${((o.open - o.overdue) / max) * 100}%` }} />
                        </div>
                      </Link>
                    );
                  })}
                  {!d.by_owner.length && <Empty title="No open items" />}
                </div>
              </div>
            </div>
          </div>
          <ItemDrawer itemId={openItem} onClose={() => setOpenItem(null)} onChanged={state.reload} people={people} />
        </div>
      )}
    </PageLoader>
  );
}
