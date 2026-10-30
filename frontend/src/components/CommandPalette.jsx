import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BellRing, BookOpen, CheckSquare, Columns3, CornerDownLeft, LayoutDashboard, MessageCircleQuestion, Search, Users } from "lucide-react";
import { api, fmtDate } from "../api";

const PAGES = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard },
  { label: "Meetings & handovers", to: "/meetings", icon: Users },
  { label: "Action items board", to: "/items", icon: Columns3 },
  { label: "Follow-up autopilot", to: "/followups", icon: BellRing },
  { label: "Knowledge base", to: "/knowledge", icon: BookOpen },
  { label: "Ask team memory", to: "/ask", icon: MessageCircleQuestion },
];

/**
 * Cmd/Ctrl + K palette: one search box over pages, meetings, open items and documents.
 * Arrow keys move, Enter opens, Esc closes. Data is fetched when it opens, so it's always fresh.
 */
export default function CommandPalette() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [data, setData] = useState({ meetings: [], items: [], docs: [] });
  const [active, setActive] = useState(0);
  const listRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("open-palette", onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("open-palette", onOpen); };
  }, []);

  useEffect(() => {
    if (!open) return;
    setQ(""); setActive(0);
    Promise.all([api.get("/meetings"), api.get("/items?status=open"), api.get("/knowledge")])
      .then(([meetings, items, docs]) => setData({ meetings, items, docs }))
      .catch(() => {});
  }, [open]);

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    const hit = (s) => !term || s.toLowerCase().includes(term);
    const out = [];
    PAGES.filter((p) => hit(p.label)).forEach((p) => out.push({ group: "Go to", label: p.label, icon: p.icon, to: p.to }));
    data.meetings.filter((m) => hit(m.title)).slice(0, 6).forEach((m) =>
      out.push({ group: "Meetings", label: m.title, hint: `${m.kind} · ${fmtDate(m.scheduled_at)}`, icon: Users, to: `/meetings/${m.id}` }));
    data.items.filter((i) => hit(`${i.title} ${i.owner}`)).slice(0, 6).forEach((i) =>
      out.push({ group: "Open items", label: i.title, hint: `${i.owner || "Unassigned"}${i.is_overdue ? " · overdue" : ""}`, icon: CheckSquare, to: `/meetings/${i.current_meeting_id}` }));
    data.docs.filter((d) => hit(`${d.title} ${d.tags.join(" ")} ${d.content}`)).slice(0, 5).forEach((d) =>
      out.push({ group: "Knowledge", label: d.title, hint: d.doc_type, icon: BookOpen, to: `/knowledge?doc=${d.id}` }));
    if (term.length > 3) out.push({ group: "Ask AI", label: `Ask the team memory: “${q.trim()}”`, icon: MessageCircleQuestion, to: `/ask?q=${encodeURIComponent(q.trim())}` });
    return out;
  }, [q, data]);

  useEffect(() => { setActive(0); }, [q]);
  useEffect(() => { listRef.current?.querySelector(`[data-idx='${active}']`)?.scrollIntoView({ block: "nearest" }); }, [active]);

  if (!open) return null;
  const go = (r) => { setOpen(false); nav(r.to); };
  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    if (e.key === "Enter" && results[active]) go(results[active]);
  };

  let lastGroup = null;
  return (
    <div className="fixed inset-0 z-50 bg-ink-900/50 backdrop-blur-sm flex items-start justify-center p-4 pt-[12vh]" onMouseDown={() => setOpen(false)}>
      <div className="card w-full max-w-xl shadow-2xl overflow-hidden animate-pop" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 border-b border-slate-100">
          <Search className="w-4 h-4 text-slate-400" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKeyDown}
            className="flex-1 py-3.5 text-sm outline-none bg-transparent" placeholder="Search meetings, items, documents… or ask a question" />
          <kbd className="text-[10px] text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">esc</kbd>
        </div>
        <div ref={listRef} className="max-h-[50vh] overflow-y-auto py-1">
          {results.map((r, idx) => {
            const header = r.group !== lastGroup ? <div className="px-4 pt-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{r.group}</div> : null;
            lastGroup = r.group;
            const Icon = r.icon;
            return (
              <div key={`${r.group}-${idx}`}>
                {header}
                <button data-idx={idx} onMouseEnter={() => setActive(idx)} onClick={() => go(r)}
                  className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm ${idx === active ? "bg-brand-50 text-brand-900" : "text-slate-700"}`}>
                  <Icon className={`w-4 h-4 shrink-0 ${idx === active ? "text-brand-600" : "text-slate-400"}`} />
                  <span className="flex-1 truncate">{r.label}</span>
                  {r.hint && <span className="text-xs text-slate-400 shrink-0">{r.hint}</span>}
                  {idx === active && <CornerDownLeft className="w-3.5 h-3.5 text-brand-500" />}
                </button>
              </div>
            );
          })}
          {!results.length && <div className="px-4 py-8 text-center text-sm text-slate-400">No matches</div>}
        </div>
        <div className="px-4 py-2 border-t border-slate-100 text-[11px] text-slate-400 flex gap-4">
          <span>↑↓ move</span><span>↵ open</span><span>⌘K toggle</span>
        </div>
      </div>
    </div>
  );
}
