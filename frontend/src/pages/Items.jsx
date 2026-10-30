import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ListChecks, Search } from "lucide-react";
import { api } from "../api";
import { Empty, PageLoader, useLoad } from "../components/ui";
import ItemDrawer from "../components/ItemDrawer";
import ItemTable from "../components/ItemTable";

const VIEWS = [["open", "Open"], ["overdue", "Overdue"], ["blocked", "Blocked"], ["closed", "Closed"], ["all", "All"]];

export default function Items() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") || "open";
  const owner = params.get("owner");
  const [q, setQ] = useState("");
  const [openItem, setOpenItem] = useState(null);

  const qs = new URLSearchParams();
  if (view === "overdue") qs.set("overdue", "true");
  else if (view !== "all") qs.set("status", view);
  if (owner !== null) qs.set("owner", owner);
  if (q) qs.set("q", q);
  const key = qs.toString();
  const state = useLoad(() => Promise.all([api.get(`/items?${key}`), api.get("/people"), api.get("/meetings")]), [key]);

  const set = (k, v) => { const p = new URLSearchParams(params); v === null ? p.delete(k) : p.set(k, v); setParams(p); };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">Action items</h1>
      <div className="flex gap-2 flex-wrap items-center">
        <div className="flex rounded-lg border border-slate-300 bg-white p-0.5">
          {VIEWS.map(([v, label]) => (
            <button key={v} onClick={() => set("view", v)} className={`px-3 py-1 text-sm rounded-md ${view === v ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>{label}</button>
          ))}
        </div>
        <div className="relative flex-1 min-w-40">
          <Search className="w-4 h-4 absolute left-2.5 top-2 text-slate-400" />
          <input className="input pl-8" placeholder="Search items…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input w-auto" value={owner ?? "__all"} onChange={(e) => set("owner", e.target.value === "__all" ? null : e.target.value)}>
          <option value="__all">Everyone</option><option value="">Unassigned</option>
          {(state.data?.[1] || []).map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
      <PageLoader state={state}>
        {([items, people, meetings]) => {
          const titles = Object.fromEntries(meetings.map((m) => [m.id, `${m.title} · ${new Date(m.scheduled_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}`]));
          return (
            <>
              <div className="card">{items.length ? <ItemTable items={items} onOpen={setOpenItem} showMeeting meetingTitles={titles} /> : <Empty icon={ListChecks} title="No items in this view" />}</div>
              <ItemDrawer itemId={openItem} onClose={() => setOpenItem(null)} onChanged={state.reload} people={people} />
            </>
          );
        }}
      </PageLoader>
    </div>
  );
}
