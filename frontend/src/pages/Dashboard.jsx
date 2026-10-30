import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertOctagon, CalendarClock, CornerDownRight, Plus, ShieldAlert } from "lucide-react";
import { api, fmtDate, fmtDateTime } from "../api";
import { Empty, KindBadge, PageLoader, SeverityBadge, StatusBadge, useLoad } from "../components/ui";
import ItemDrawer from "../components/ItemDrawer";
import ItemTable from "../components/ItemTable";
import NewMeetingModal from "../components/NewMeetingModal";

function Stat({ label, value, tone = "slate", to }) {
  const tones = { slate: "text-slate-900", red: "text-red-600", amber: "text-amber-600", emerald: "text-emerald-600", violet: "text-violet-600" };
  const body = (
    <div className="card px-4 py-3 hover:border-indigo-200 transition">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold mt-0.5 ${tones[tone]}`}>{value}</div>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function Dashboard() {
  const state = useLoad(() => Promise.all([api.get("/dashboard"), api.get("/conflicts?status=open"), api.get("/people")]));
  const [openItem, setOpenItem] = useState(null);
  const [newOpen, setNewOpen] = useState(false);

  return (
    <PageLoader state={state}>
      {([d, conflicts, people]) => (
        <div className="space-y-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-xl font-semibold text-slate-900">What needs attention</h1>
              <p className="text-sm text-slate-500">Open loops across every meeting and handover.</p>
            </div>
            <button className="btn-primary" onClick={() => setNewOpen(true)}><Plus className="w-4 h-4" />New meeting or handover</button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <Stat label="Open items" value={d.counts.open} to="/items" />
            <Stat label="Overdue" value={d.counts.overdue} tone={d.counts.overdue ? "red" : "slate"} to="/items?view=overdue" />
            <Stat label="Blocked" value={d.counts.blocked} tone={d.counts.blocked ? "amber" : "slate"} />
            <Stat label="Unassigned" value={d.counts.unassigned} tone={d.counts.unassigned ? "amber" : "slate"} />
            <Stat label="Closed this week" value={d.counts.closed_this_week} tone="emerald" />
            <Stat label="Decision conflicts" value={d.counts.open_conflicts} tone={d.counts.open_conflicts ? "violet" : "slate"} />
          </div>

          {conflicts.length > 0 && (
            <div className="card border-violet-200 overflow-hidden">
              <div className="px-4 py-3 bg-violet-50 border-b border-violet-100 section-title text-violet-900">
                <ShieldAlert className="w-4 h-4" />Decisions that contradict earlier decisions or policy
              </div>
              <div className="divide-y divide-slate-100">
                {conflicts.slice(0, 4).map((c) => (
                  <Link key={c.id} to={`/meetings/${c.meeting_id}#conflicts`} className="block px-4 py-3 hover:bg-slate-50">
                    <div className="flex items-center gap-2 mb-1"><SeverityBadge severity={c.severity} /><span className="text-sm font-medium">{c.decision_text}</span></div>
                    <div className="text-xs text-slate-500">vs. <span className="font-medium text-slate-600">{c.conflicting_source_title}</span> — {c.explanation}</div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <div className="card">
                <div className="px-4 py-3 border-b border-slate-100 section-title"><CalendarClock className="w-4 h-4 text-red-500" />Overdue</div>
                {d.overdue.length ? <ItemTable items={d.overdue} onOpen={setOpenItem} /> : <Empty title="Nothing overdue" hint="Nice." />}
              </div>
              <div className="card">
                <div className="px-4 py-3 border-b border-slate-100">
                  <div className="section-title"><CornerDownRight className="w-4 h-4 text-orange-500" />Going stale</div>
                  <div className="text-xs text-slate-500 mt-0.5">Carried forward 2+ times without closing — these are the items that quietly die.</div>
                </div>
                {d.stale.length ? <ItemTable items={d.stale} onOpen={setOpenItem} /> : <Empty title="No stale items" />}
              </div>
            </div>
            <div className="space-y-6">
              <div className="card">
                <div className="px-4 py-3 border-b border-slate-100 section-title">Upcoming</div>
                {d.upcoming.length ? (
                  <div className="divide-y divide-slate-100">
                    {d.upcoming.map((m) => (
                      <Link key={m.id} to={`/meetings/${m.id}`} className="block px-4 py-3 hover:bg-slate-50">
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
                <div className="px-4 py-3 border-b border-slate-100 section-title">Open items by owner</div>
                <div className="p-4 space-y-2.5">
                  {d.by_owner.map((o) => {
                    const max = Math.max(...d.by_owner.map((x) => x.open));
                    return (
                      <Link key={o.owner} to={`/items?owner=${encodeURIComponent(o.owner === "Unassigned" ? "" : o.owner)}`} className="block group">
                        <div className="flex justify-between text-xs mb-1">
                          <span className={`font-medium group-hover:text-indigo-600 ${o.owner === "Unassigned" ? "text-red-600" : ""}`}>{o.owner}</span>
                          <span className="text-slate-500">{o.open} open{o.overdue ? <span className="text-red-600"> · {o.overdue} overdue</span> : null}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden flex">
                          <div className="bg-red-500" style={{ width: `${(o.overdue / max) * 100}%` }} />
                          <div className="bg-indigo-500" style={{ width: `${((o.open - o.overdue) / max) * 100}%` }} />
                        </div>
                      </Link>
                    );
                  })}
                  {!d.by_owner.length && <Empty icon={AlertOctagon} title="No open items" />}
                </div>
              </div>
            </div>
          </div>
          <ItemDrawer itemId={openItem} onClose={() => setOpenItem(null)} onChanged={state.reload} people={people} />
          <NewMeetingModal open={newOpen} onClose={() => setNewOpen(false)} people={people} />
          <div className="text-[11px] text-slate-400 text-right">Data as of {fmtDate(new Date().toISOString())}</div>
        </div>
      )}
    </PageLoader>
  );
}
