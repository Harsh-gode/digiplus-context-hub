import { useState } from "react";
import { CalendarClock, CheckCircle2, CircleDot, CornerDownRight, GripVertical, Loader, OctagonX } from "lucide-react";
import { api, fmtDate } from "../api";
import { Modal, PriorityBadge, SourceTag, useAction } from "./ui";

const COLUMNS = [
  { status: "open", title: "Open", icon: CircleDot, tone: "text-sky-600", ring: "ring-sky-300 bg-sky-50/60" },
  { status: "in_progress", title: "In progress", icon: Loader, tone: "text-amber-600", ring: "ring-amber-300 bg-amber-50/60" },
  { status: "blocked", title: "Blocked", icon: OctagonX, tone: "text-red-600", ring: "ring-red-300 bg-red-50/60" },
  { status: "done", title: "Done (last 14 days)", icon: CheckCircle2, tone: "text-emerald-600", ring: "ring-emerald-300 bg-emerald-50/60" },
];

const initials = (name) => name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();

/**
 * Kanban board for action items.
 * Drag a card to another column to change its status (saved immediately, rolled back if the server refuses).
 * Dropping on "Done" asks for the outcome first, because closing requires one.
 */
export default function Board({ items, setItems, onOpen }) {
  const [dragId, setDragId] = useState(null);
  const [overCol, setOverCol] = useState(null);
  const [closing, setClosing] = useState(null); // item waiting for an outcome
  const [outcome, setOutcome] = useState("");
  const [run, busy] = useAction();

  const recentCutoff = Date.now() - 14 * 864e5;
  const inColumn = (status) =>
    items.filter((i) =>
      status === "done" ? ["done", "dropped"].includes(i.status) && new Date(i.closed_at || i.updated_at).getTime() >= recentCutoff : i.status === status
    );

  const move = async (item, status) => {
    if (!item || item.status === status) return;
    if (status === "done") { setClosing(item); setOutcome(""); return; }
    const before = items;
    setItems(items.map((i) => (i.id === item.id ? { ...i, status } : i))); // optimistic
    const wasClosed = ["done", "dropped"].includes(item.status);
    const r = await run(() => api.patch(`/items/${item.id}`, { status, note: wasClosed ? "Reopened from board" : "Moved on board" }), `Moved to ${status.replace("_", " ")}`);
    if (!r) setItems(before); // server refused → put it back
    else setItems((cur) => cur.map((i) => (i.id === r.id ? { ...i, ...r } : i)));
  };

  const confirmClose = async () => {
    const r = await run(() => api.post(`/items/${closing.id}/close`, { status: "done", outcome }), "Closed — outcome recorded");
    if (r) { setItems(items.map((i) => (i.id === r.id ? { ...i, ...r } : i))); setClosing(null); }
  };

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 items-start">
        {COLUMNS.map((col) => {
          const list = inColumn(col.status);
          const Icon = col.icon;
          return (
            <section
              key={col.status}
              onDragOver={(e) => { e.preventDefault(); setOverCol(col.status); }}
              onDragLeave={() => setOverCol((c) => (c === col.status ? null : c))}
              onDrop={(e) => { e.preventDefault(); setOverCol(null); move(items.find((i) => i.id === dragId), col.status); setDragId(null); }}
              className={`rounded-xl bg-slate-100/70 p-2.5 min-h-40 transition ${overCol === col.status ? `ring-2 ${col.ring}` : ""}`}
            >
              <header className="flex items-center justify-between px-1.5 pb-2">
                <span className={`flex items-center gap-1.5 text-sm font-semibold ${col.tone}`}><Icon className="w-4 h-4" />{col.title}</span>
                <span className="chip bg-white text-slate-500">{list.length}</span>
              </header>
              <div className="space-y-2">
                {list.map((i) => (
                  <article
                    key={i.id}
                    draggable
                    onDragStart={(e) => { setDragId(i.id); e.dataTransfer.effectAllowed = "move"; }}
                    onDragEnd={() => setDragId(null)}
                    onClick={() => onOpen(i.id)}
                    className={`card card-hover p-3 cursor-grab active:cursor-grabbing animate-pop group ${dragId === i.id ? "opacity-40" : ""} ${i.is_overdue ? "border-l-4 border-l-red-500" : ""}`}
                  >
                    <div className="flex gap-1.5">
                      <GripVertical className="w-3.5 h-3.5 text-slate-300 mt-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition" />
                      <div className={`text-sm font-medium leading-snug ${col.status === "done" ? "line-through text-slate-400" : ""}`}>{i.title}</div>
                    </div>
                    <div className="flex flex-wrap gap-1 mt-2">
                      <PriorityBadge priority={i.priority} />
                      <SourceTag source={i.source} />
                      {i.times_carried > 0 && <span className="chip bg-orange-50 text-orange-700"><CornerDownRight className="w-3 h-3" />{i.times_carried}×</span>}
                    </div>
                    <div className="flex items-center justify-between mt-2.5 text-xs">
                      <span className={`flex items-center gap-1 ${i.is_overdue ? "text-red-600 font-medium" : "text-slate-500"}`}>
                        {i.is_overdue && <CalendarClock className="w-3.5 h-3.5" />}{i.due_date ? fmtDate(i.due_date) : "No due date"}
                      </span>
                      {i.owner ? (
                        <span title={i.owner} className="w-6 h-6 rounded-full bg-brand-100 text-brand-700 grid place-items-center text-[10px] font-semibold">{initials(i.owner)}</span>
                      ) : (
                        <span className="text-red-500 font-medium">Unassigned</span>
                      )}
                    </div>
                  </article>
                ))}
                {!list.length && <div className="text-xs text-slate-400 text-center py-6 border-2 border-dashed border-slate-200 rounded-lg">Drop items here</div>}
              </div>
            </section>
          );
        })}
      </div>

      <Modal open={!!closing} onClose={() => setClosing(null)} title="Close item — what was the outcome?">
        {closing && (
          <div className="space-y-3">
            <div className="text-sm font-medium">{closing.title}</div>
            <textarea autoFocus className="input min-h-24" value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="What actually happened? (required, min 5 characters)" />
            <div className="flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => setClosing(null)}>Cancel</button>
              <button className="btn-primary bg-emerald-600 hover:bg-emerald-700" disabled={busy || outcome.trim().length < 5} onClick={confirmClose}>Close item</button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
