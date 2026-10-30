import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, CornerDownRight, History, RotateCcw, UserRound, X } from "lucide-react";
import { api, fmtDate, fmtDateTime } from "../api";
import { Field, PriorityBadge, SourceTag, Spinner, StatusBadge, useAction } from "./ui";

const EVENT_LABEL = {
  created: "Created",
  reassigned: "Reassigned",
  status_changed: "Status changed",
  due_changed: "Due date changed",
  carried_forward: "Carried forward",
  closed: "Closed",
  reopened: "Reopened",
  nudged: "Follow-up sent",
  title_changed: "Renamed",
  priority_changed: "Priority changed",
  description_changed: "Description edited",
};

// Side panel for one action item: edit, reassign, close with outcome, and full history.
export default function ItemDrawer({ itemId, onClose, onChanged, people = [] }) {
  const [item, setItem] = useState(null);
  const [form, setForm] = useState(null);
  const [outcome, setOutcome] = useState("");
  const [closeStatus, setCloseStatus] = useState("done");
  const [run, busy] = useAction();

  const load = () => api.get(`/items/${itemId}`).then((d) => { setItem(d); setForm({ owner: d.owner, due_date: d.due_date || "", status: d.status, priority: d.priority, note: "" }); });
  useEffect(() => { if (itemId) load(); }, [itemId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!itemId) return null;
  const closed = item && ["done", "dropped"].includes(item.status);

  const save = async () => {
    const body = {};
    if (form.owner !== item.owner) body.owner = form.owner;
    if ((form.due_date || null) !== (item.due_date || null)) body.due_date = form.due_date || null;
    if (form.status !== item.status) body.status = form.status;
    if (form.priority !== item.priority) body.priority = form.priority;
    if (!Object.keys(body).length) return;
    body.note = form.note;
    const r = await run(() => api.patch(`/items/${itemId}`, body), "Item updated");
    if (r) { setItem(r); setForm({ ...form, note: "" }); onChanged?.(); }
  };
  const close = async () => {
    const r = await run(() => api.post(`/items/${itemId}/close`, { status: closeStatus, outcome }), "Item closed — outcome recorded");
    if (r) { setItem(r); setOutcome(""); onChanged?.(); }
  };
  const reopen = async () => {
    const r = await run(() => api.patch(`/items/${itemId}`, { status: "open", note: "Reopened" }), "Item reopened");
    if (r) { setItem(r); setForm((f) => ({ ...f, status: "open" })); onChanged?.(); }
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink-900/30" onMouseDown={onClose}>
      <aside className="w-full max-w-md h-full bg-white shadow-xl overflow-y-auto" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 sticky top-0 bg-white">
          <span className="text-xs font-medium text-slate-500">Action item #{itemId}</span>
          <button className="btn-ghost p-1" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        {!item ? (
          <div className="p-10 flex justify-center"><Spinner /></div>
        ) : (
          <div className="p-5 space-y-5">
            <div>
              <h2 className="font-semibold text-lg leading-snug">{item.title}</h2>
              <div className="flex flex-wrap gap-1.5 mt-2">
                <StatusBadge status={item.status} />
                <PriorityBadge priority={item.priority} />
                <SourceTag source={item.source} />
                {item.is_overdue && <span className="chip bg-red-600 text-white">overdue</span>}
                {item.times_carried > 0 && <span className="chip bg-orange-50 text-orange-700">carried {item.times_carried}×</span>}
              </div>
              <div className="text-xs text-slate-500 mt-3 space-y-1">
                <div>Raised in <Link className="text-brand-600 hover:underline" to={`/meetings/${item.origin_meeting_id}`}>{item.origin_meeting_title}</Link></div>
                {item.current_meeting_id !== item.origin_meeting_id && (
                  <div>Now tracked in <Link className="text-brand-600 hover:underline" to={`/meetings/${item.current_meeting_id}`}>{item.current_meeting_title}</Link></div>
                )}
              </div>
            </div>

            {closed ? (
              <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-3">
                <div className="text-xs font-semibold text-emerald-800 mb-1 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Outcome · {fmtDate(item.closed_at)}</div>
                <div className="text-sm text-emerald-900">{item.outcome}</div>
                <button className="btn-ghost mt-2 -ml-2" onClick={reopen} disabled={busy}><RotateCcw className="w-3.5 h-3.5" />Reopen</button>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Owner">
                    <input className="input" list="people-list" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} placeholder="Unassigned" />
                    <datalist id="people-list">{people.map((p) => <option key={p} value={p} />)}</datalist>
                  </Field>
                  <Field label="Due date"><input type="date" className="input" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></Field>
                  <Field label="Status">
                    <select className="input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                      <option value="open">Open</option><option value="in_progress">In progress</option><option value="blocked">Blocked</option>
                    </select>
                  </Field>
                  <Field label="Priority">
                    <select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                      <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
                    </select>
                  </Field>
                </div>
                <Field label="Comment for history (optional)"><input className="input" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="e.g. Reassigned while Rahul is on leave" /></Field>
                <button className="btn-primary" onClick={save} disabled={busy}>Save changes</button>

                <div className="border-t border-slate-100 pt-4">
                  <div className="section-title mb-2"><CheckCircle2 className="w-4 h-4 text-emerald-600" />Close with outcome</div>
                  <textarea className="input min-h-20" value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="What actually happened? (required, min 5 characters)" />
                  <div className="flex gap-2 mt-2">
                    <select className="input w-auto" value={closeStatus} onChange={(e) => setCloseStatus(e.target.value)}>
                      <option value="done">Done</option><option value="dropped">Dropped</option>
                    </select>
                    <button className="btn-primary bg-emerald-600 hover:bg-emerald-700" disabled={busy || outcome.trim().length < 5} onClick={close}>Close item</button>
                  </div>
                </div>
              </>
            )}

            <div className="border-t border-slate-100 pt-4">
              <div className="section-title mb-3"><History className="w-4 h-4 text-slate-500" />History</div>
              <ol className="relative border-l border-slate-200 ml-1.5 space-y-3">
                {item.history.map((h) => (
                  <li key={h.id} className="ml-4">
                    <span className={`absolute -left-1.5 w-3 h-3 rounded-full border-2 border-white ${h.event === "closed" ? "bg-emerald-500" : h.event === "carried_forward" ? "bg-orange-400" : h.event === "reassigned" ? "bg-violet-500" : h.event === "nudged" ? "bg-pink-500" : "bg-slate-300"}`} />
                    <div className="text-sm font-medium flex items-center gap-1">
                      {h.event === "reassigned" && <UserRound className="w-3.5 h-3.5 text-violet-500" />}
                      {h.event === "carried_forward" && <CornerDownRight className="w-3.5 h-3.5 text-orange-500" />}
                      {EVENT_LABEL[h.event] || h.event}
                    </div>
                    {(h.from_value || h.to_value) && h.event !== "created" && (
                      <div className="text-xs text-slate-500 flex items-center gap-1 flex-wrap">
                        <span>{h.from_value || "—"}</span><ArrowRight className="w-3 h-3" /><span>{h.to_value || "—"}</span>
                      </div>
                    )}
                    {h.note && <div className="text-xs text-slate-500 italic">{h.note}</div>}
                    <div className="text-[11px] text-slate-400">{fmtDateTime(h.created_at)}</div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
