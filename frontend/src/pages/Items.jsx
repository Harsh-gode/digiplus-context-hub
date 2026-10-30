import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Columns3, List, ListChecks, Search } from "lucide-react";
import { api } from "../api";
import { Empty, PageLoader, useLoad } from "../components/ui";
import Board from "../components/Board";
import ItemDrawer from "../components/ItemDrawer";
import ItemTable from "../components/ItemTable";

const VIEWS = [["open", "Open"], ["overdue", "Overdue"], ["blocked", "Blocked"], ["closed", "Closed"], ["all", "All"]];

export default function Items() {
  const [params, setParams] = useSearchParams();
  const layout = params.get("layout") || "board";
  const view = params.get("view") || "open";
  const owner = params.get("owner");
  const [q, setQ] = useState("");
  const [openItem, setOpenItem] = useState(null);

  // The board always shows every status (it IS the status view); the list uses the status tabs.
  const qs = new URLSearchParams();
  if (layout === "list") {
    if (view === "overdue") qs.set("overdue", "true");
    else if (view !== "all") qs.set("status", view);
  }
  if (owner !== null) qs.set("owner", owner);
  if (q) qs.set("q", q);
  const key = qs.toString();
  const state = useLoad(() => Promise.all([api.get(`/items?${key}`), api.get("/people"), api.get("/meetings")]), [key]);

  const set = (k, v) => { const p = new URLSearchParams(params); v === null ? p.delete(k) : p.set(k, v); setParams(p); };
  const setItems = (updater) => state.setData([typeof updater === "function" ? updater(state.data[0]) : updater, state.data[1], state.data[2]]);

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="eyebrow mb-2"><span className="w-6 h-px bg-brand-600" />Follow-through</div><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Action <span className="text-gradient">items</span></h1>
          <p className="text-sm text-slate-500">{layout === "board" ? "Drag cards between columns to update status. Dropping on Done asks for the outcome." : "Every item across all meetings and handovers."}</p>
        </div>
        <div className="flex rounded-lg border border-slate-300 bg-white p-0.5">
          {[["board", "Board", Columns3], ["list", "List", List]].map(([v, label, Icon]) => (
            <button key={v} onClick={() => set("layout", v)} className={`flex items-center gap-1.5 px-3 py-1 text-sm rounded-md transition ${layout === v ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>
              <Icon className="w-4 h-4" />{label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        {layout === "list" && (
          <div className="flex rounded-lg border border-slate-300 bg-white p-0.5">
            {VIEWS.map(([v, label]) => (
              <button key={v} onClick={() => set("view", v)} className={`px-3 py-1 text-sm rounded-md transition ${view === v ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>{label}</button>
            ))}
          </div>
        )}
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
              {layout === "board" ? (
                <Board items={items} setItems={setItems} onOpen={setOpenItem} />
              ) : (
                <div className="card">{items.length ? <ItemTable items={items} onOpen={setOpenItem} showMeeting meetingTitles={titles} /> : <Empty icon={ListChecks} title="No items in this view" />}</div>
              )}
              <ItemDrawer itemId={openItem} onClose={() => setOpenItem(null)} onChanged={state.reload} people={people} />
            </>
          );
        }}
      </PageLoader>
    </div>
  );
}
