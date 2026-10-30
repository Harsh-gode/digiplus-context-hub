import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, Plus, Search, ShieldAlert } from "lucide-react";
import { api, fmtDateTime } from "../api";
import { Empty, KindBadge, PageLoader, StatusBadge, useLoad } from "../components/ui";
import NewMeetingModal from "../components/NewMeetingModal";

export default function Meetings() {
  const [filters, setFilters] = useState({ kind: "", status: "", q: "" });
  const [newOpen, setNewOpen] = useState(false);
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
  const state = useLoad(() => Promise.all([api.get(`/meetings?${qs}`), api.get("/people")]), [qs]);

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div><div className="eyebrow mb-2"><span className="w-6 h-px bg-brand-600" />Workspace</div><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Meetings & <span className="text-gradient">handovers</span></h1></div>
        <button className="btn-primary" onClick={() => setNewOpen(true)}><Plus className="w-4 h-4" />New</button>
      </div>
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="w-4 h-4 absolute left-2.5 top-2 text-slate-400" />
          <input className="input pl-8" placeholder="Search title, agenda, summary…" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        </div>
        <select className="input w-auto" value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })}>
          <option value="">All types</option><option value="meeting">Meetings</option><option value="handover">Handovers</option>
        </select>
        <select className="input w-auto" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
          <option value="">Any status</option><option value="scheduled">Scheduled</option><option value="in_progress">In progress</option>
          <option value="completed">Completed</option><option value="cancelled">Cancelled</option>
        </select>
      </div>
      <PageLoader state={state}>
        {([meetings, people]) => (
          <>
            <div className="card divide-y divide-slate-100">
              {meetings.map((m) => (
                <Link key={m.id} to={`/meetings/${m.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50">
                  <div className="w-11 text-center shrink-0">
                    <div className="text-[10px] uppercase text-slate-400">{new Date(m.scheduled_at).toLocaleString(undefined, { month: "short" })}</div>
                    <div className="text-lg font-semibold leading-none">{new Date(m.scheduled_at).getDate()}</div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{m.title}</div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 flex-wrap">
                      <KindBadge kind={m.kind} /><StatusBadge status={m.status} />
                      <span>{fmtDateTime(m.scheduled_at)}</span>
                      <span>· {m.participant_count} people</span>
                      {m.kind === "handover" && <span>· {m.handover_from || "?"} → {m.handover_to}</span>}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    {m.open_conflicts > 0 && <span className="chip bg-violet-100 text-violet-700"><ShieldAlert className="w-3 h-3" />{m.open_conflicts}</span>}
                    {m.open_item_count > 0 && <span className="chip bg-sky-50 text-sky-700">{m.open_item_count} open</span>}
                  </div>
                </Link>
              ))}
              {!meetings.length && <Empty icon={CalendarDays} title="No meetings match" hint="Try clearing filters, or create one." />}
            </div>
            <NewMeetingModal open={newOpen} onClose={() => setNewOpen(false)} people={people} />
          </>
        )}
      </PageLoader>
    </div>
  );
}
