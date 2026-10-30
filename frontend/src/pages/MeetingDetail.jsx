import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, ChevronRight, FileText, Gavel, Link2, ListChecks, MessageSquareText,
  Pencil, Plus, RefreshCw, ShieldAlert, Sparkles, Trash2, UserCheck, UserX, Wand2, X,
} from "lucide-react";
import { api, fmtDate, fmtDateTime } from "../api";
import {
  AIBanner, Empty, Field, KindBadge, Markdown, PageLoader, PriorityBadge, SeverityBadge, SourceTag, Spinner, StatusBadge, useAction, useLoad,
} from "../components/ui";
import ItemDrawer from "../components/ItemDrawer";
import ItemTable from "../components/ItemTable";
import NewMeetingModal from "../components/NewMeetingModal";

const TRANSITIONS = {
  scheduled: [["in_progress", "Start"], ["completed", "Mark completed"], ["cancelled", "Cancel"]],
  in_progress: [["completed", "Mark completed"], ["cancelled", "Cancel"]],
  completed: [["in_progress", "Reopen"]],
  cancelled: [["scheduled", "Restore"]],
};

function Card({ title, icon: Icon, actions, children, id, className = "" }) {
  return (
    <section id={id} className={`card ${className}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 gap-2">
        <div className="section-title">{Icon && <Icon className="w-4 h-4 text-slate-500" />}{title}</div>
        <div className="flex gap-1">{actions}</div>
      </div>
      {children}
    </section>
  );
}

// ---------------- AI capture: raw text -> reviewed recap ----------------
function CaptureRecap({ meeting, onSaved, people }) {
  const [raw, setRaw] = useState("");
  const [source, setSource] = useState("notes");
  const [draft, setDraft] = useState(null);
  const [run, busy] = useAction();
  const [saving, setSaving] = useState(false);

  const generate = async (useExisting) => {
    const body = useExisting ? { save_note: false } : { raw_text: raw, source, save_note: true };
    const r = await run(() => api.post(`/meetings/${meeting.id}/extract`, body));
    if (r) { setDraft(r); if (!useExisting) setRaw(""); onSaved(false); }
  };
  const save = async () => {
    setSaving(true);
    const r = await run(
      () => api.post(`/meetings/${meeting.id}/apply-recap`, { summary: draft.summary, decisions: draft.decisions, action_items: draft.action_items, source: draft.ai_status === "ok" ? "ai" : "fallback" }),
      "Recap saved · knowledge linked · decisions checked for conflicts"
    );
    setSaving(false);
    if (r) { setDraft(null); onSaved(true, r); }
  };
  const upd = (key, idx, patch) => setDraft({ ...draft, [key]: draft[key].map((x, i) => (i === idx ? { ...x, ...patch } : x)) });
  const del = (key, idx) => setDraft({ ...draft, [key]: draft[key].filter((_, i) => i !== idx) });

  if (draft)
    return (
      <Card title="Review AI recap before saving" icon={Sparkles} className="border-indigo-200 ring-4 ring-indigo-50"
        actions={<button className="btn-ghost" onClick={() => setDraft(null)}><X className="w-4 h-4" />Discard</button>}>
        <div className="p-4 space-y-4">
          <AIBanner status={draft.ai_status} message={draft.ai_message} />
          <Field label="Summary"><textarea className="input min-h-20" value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} /></Field>
          <div>
            <div className="label">Decisions ({draft.decisions.length})</div>
            <div className="space-y-2">
              {draft.decisions.map((d, i) => (
                <div key={i} className="flex gap-2">
                  <input className="input" value={d.text} onChange={(e) => upd("decisions", i, { text: e.target.value })} />
                  <button className="btn-ghost" onClick={() => del("decisions", i)} aria-label="Remove"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
              <button className="btn-ghost text-xs" onClick={() => setDraft({ ...draft, decisions: [...draft.decisions, { text: "", rationale: "" }] })}><Plus className="w-3.5 h-3.5" />Add decision</button>
            </div>
          </div>
          <div>
            <div className="label">Action items ({draft.action_items.length})</div>
            <div className="space-y-2">
              {draft.action_items.map((a, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-center">
                  <input className="input col-span-12 md:col-span-6" value={a.title} onChange={(e) => upd("action_items", i, { title: e.target.value })} />
                  <input className={`input col-span-4 md:col-span-2 ${!a.owner ? "border-amber-300 bg-amber-50" : ""}`} list="cap-people" placeholder="Owner?" value={a.owner} onChange={(e) => upd("action_items", i, { owner: e.target.value })} />
                  <input type="date" className="input col-span-4 md:col-span-2" value={a.due_date || ""} onChange={(e) => upd("action_items", i, { due_date: e.target.value || null })} />
                  <select className="input col-span-3 md:col-span-1 px-1" value={a.priority} onChange={(e) => upd("action_items", i, { priority: e.target.value })}>
                    <option value="low">low</option><option value="medium">med</option><option value="high">high</option>
                  </select>
                  <button className="btn-ghost col-span-1 justify-center" onClick={() => del("action_items", i)} aria-label="Remove"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
              <datalist id="cap-people">{people.map((p) => <option key={p} value={p} />)}</datalist>
              <button className="btn-ghost text-xs" onClick={() => setDraft({ ...draft, action_items: [...draft.action_items, { title: "", owner: "", due_date: null, priority: "medium" }] })}><Plus className="w-3.5 h-3.5" />Add item</button>
            </div>
          </div>
          {draft.open_questions?.length > 0 && (
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="label">Open questions spotted</div>
              <ul className="list-disc pl-5 text-sm text-slate-600">{draft.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
            </div>
          )}
          <div className="flex justify-end">
            <button className="btn-primary" onClick={save} disabled={saving}>{saving ? <Spinner /> : <Check className="w-4 h-4" />}Save to {meeting.kind}</button>
          </div>
        </div>
      </Card>
    );

  return (
    <Card title="Capture what happened" icon={Wand2}>
      <div className="p-4 space-y-3">
        <textarea className="input min-h-32 font-mono text-[13px]" value={raw} onChange={(e) => setRaw(e.target.value)}
          placeholder={"Paste anything: rough notes, a Teams/Slack export, an email thread or a transcript.\n\nAI turns it into a summary, decisions and action items with owners and due dates — you review before anything is saved."} />
        <div className="flex gap-2 flex-wrap items-center">
          <select className="input w-auto" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="notes">Notes</option><option value="transcript">Transcript</option><option value="chat">Chat log</option><option value="email">Email</option><option value="document">Document</option>
          </select>
          <button className="btn-primary" disabled={busy || raw.trim().length < 10} onClick={() => generate(false)}>{busy ? <Spinner /> : <Sparkles className="w-4 h-4" />}Generate recap</button>
          {meeting.notes.length > 0 && <button className="btn-secondary" disabled={busy} onClick={() => generate(true)}>Re-analyse saved notes ({meeting.notes.length})</button>}
        </div>
      </div>
    </Card>
  );
}

// ---------------- Catch-up brief ----------------
function BriefPanel({ meeting }) {
  const absent = meeting.participants.filter((p) => !p.attended).map((p) => p.name);
  const defaultPerson = meeting.kind === "handover" ? meeting.handover_to : absent[0] || "";
  const [person, setPerson] = useState(defaultPerson);
  const [reason, setReason] = useState(meeting.kind === "handover" ? "takeover" : "missed");
  const [brief, setBrief] = useState(null);
  const [run, busy] = useAction();
  useEffect(() => { setPerson(defaultPerson); setBrief(null); }, [meeting.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = async () => {
    const r = await run(() => api.get(`/meetings/${meeting.id}/brief?person=${encodeURIComponent(person)}&reason=${reason}`));
    if (r) setBrief(r);
  };
  return (
    <Card title="Catch-up brief" icon={MessageSquareText}>
      <div className="p-4 space-y-3">
        <p className="text-xs text-slate-500">For someone who missed this, or is taking over the work.</p>
        <input className="input" list="brief-people" placeholder="Who is it for?" value={person} onChange={(e) => setPerson(e.target.value)} />
        <datalist id="brief-people">{meeting.participants.map((p) => <option key={p.id} value={p.name}>{p.attended ? "" : "absent"}</option>)}</datalist>
        <div className="flex gap-2">
          <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="missed">Missed the meeting</option><option value="takeover">Taking over the work</option>
          </select>
          <button className="btn-primary shrink-0" onClick={go} disabled={busy || !person.trim()}>{busy ? <Spinner /> : <Sparkles className="w-4 h-4" />}Brief</button>
        </div>
        {brief && (
          <div className="rounded-lg bg-indigo-50/50 border border-indigo-100 p-3 space-y-2">
            <AIBanner status={brief.ai_status} message={brief.ai_message} />
            <div className="text-xs font-medium text-indigo-700">For {brief.for_person}</div>
            <Markdown text={brief.brief} />
            <button className="btn-ghost text-xs -ml-2" onClick={() => navigator.clipboard?.writeText(brief.brief)}>Copy</button>
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------------- Decisions + conflicts (special feature) ----------------
function Decisions({ meeting, reload }) {
  const [text, setText] = useState("");
  const [run, busy] = useAction();
  const [resolving, setResolving] = useState(null);
  const [note, setNote] = useState("");
  const byDecision = meeting.conflicts.reduce((acc, c) => ({ ...acc, [c.decision_id]: [...(acc[c.decision_id] || []), c] }), {});

  const add = async (e) => {
    e.preventDefault();
    const r = await run(() => api.post(`/meetings/${meeting.id}/decisions`, { text }), "Decision recorded · checked against past decisions & policies");
    if (r) { setText(""); reload(r); }
  };
  const remove = async (id) => { const r = await run(() => api.del(`/meetings/${meeting.id}/decisions/${id}`)); if (r !== undefined) reload(); };
  const resolve = async (id, status) => {
    const r = await run(() => api.post(`/conflicts/${id}/resolve`, { status, resolution_note: note }), status === "accepted" ? "Marked as intentional change" : "Dismissed");
    if (r) { setResolving(null); setNote(""); reload(); }
  };
  const recheck = async () => { const r = await run(() => api.post(`/meetings/${meeting.id}/check-conflicts`), "Re-checked decisions"); if (r) reload(); };

  return (
    <Card id="conflicts" title={`Decisions (${meeting.decisions.length})`} icon={Gavel}
      actions={meeting.decisions.length > 0 && <button className="btn-ghost text-xs" onClick={recheck} disabled={busy} title="Check every decision against past decisions and the knowledge base"><ShieldAlert className="w-3.5 h-3.5" />Check conflicts</button>}>
      <div className="divide-y divide-slate-100">
        {meeting.decisions.map((d) => (
          <div key={d.id} className="px-4 py-3">
            <div className="flex gap-2 items-start group">
              <Gavel className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="text-sm">{d.text} <SourceTag source={d.source} /></div>
                {d.rationale && <div className="text-xs text-slate-500 mt-0.5">Why: {d.rationale}</div>}
              </div>
              <button className="opacity-0 group-hover:opacity-100 btn-ghost p-1" onClick={() => remove(d.id)} aria-label="Delete decision"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
            {(byDecision[d.id] || []).map((c) => (
              <div key={c.id} className={`mt-2 ml-6 rounded-lg border p-3 text-sm ${c.status === "open" ? "border-violet-200 bg-violet-50" : "border-slate-200 bg-slate-50 opacity-70"}`}>
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <ShieldAlert className="w-4 h-4 text-violet-600" />
                  <span className="font-medium text-violet-900">Conflicts with {c.conflicting_doc_id ? "policy" : "earlier decision"}:</span>
                  {c.conflicting_meeting_id ? <Link className="text-indigo-600 hover:underline" to={`/meetings/${c.conflicting_meeting_id}`}>{c.conflicting_source_title}</Link> : <Link className="text-indigo-600 hover:underline" to="/knowledge">{c.conflicting_source_title}</Link>}
                  <SeverityBadge severity={c.severity} />
                  {c.status !== "open" && <span className="chip bg-slate-200 text-slate-600">{c.status === "accepted" ? "intentional change" : "dismissed"}</span>}
                </div>
                {c.conflicting_text && c.conflicting_decision_id && <div className="text-xs text-slate-600 italic mb-1">“{c.conflicting_text}”</div>}
                <div className="text-slate-700">{c.explanation}</div>
                {c.suggestion && <div className="text-xs text-violet-800 mt-1"><strong>Suggested:</strong> {c.suggestion}</div>}
                {c.resolution_note && <div className="text-xs text-slate-500 mt-1">Note: {c.resolution_note}</div>}
                {c.status === "open" && (resolving === c.id ? (
                  <div className="mt-2 flex gap-2 flex-wrap">
                    <input className="input flex-1 min-w-40" placeholder="Note (e.g. CTO approved by email)" value={note} onChange={(e) => setNote(e.target.value)} />
                    <button className="btn-secondary" onClick={() => resolve(c.id, "accepted")} disabled={busy}>Intentional change</button>
                    <button className="btn-ghost" onClick={() => resolve(c.id, "dismissed")} disabled={busy}>Not a conflict</button>
                  </div>
                ) : (
                  <button className="btn-ghost text-xs mt-1 -ml-2" onClick={() => setResolving(c.id)}>Resolve…</button>
                ))}
              </div>
            ))}
          </div>
        ))}
        {!meeting.decisions.length && <Empty icon={Gavel} title="No decisions yet" hint="Generate a recap or add one below." />}
      </div>
      <form onSubmit={add} className="flex gap-2 p-3 border-t border-slate-100">
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Record a decision… (checked against past decisions & policies)" />
        <button className="btn-secondary shrink-0" disabled={busy || text.trim().length < 3}>{busy ? <Spinner /> : <Plus className="w-4 h-4" />}Add</button>
      </form>
    </Card>
  );
}

function AddItem({ meetingId, people, onAdded }) {
  const [f, setF] = useState({ title: "", owner: "", due_date: "", priority: "medium" });
  const [run, busy] = useAction();
  const submit = async (e) => {
    e.preventDefault();
    const r = await run(() => api.post(`/meetings/${meetingId}/items`, { ...f, due_date: f.due_date || null }), "Action item added");
    if (r) { setF({ title: "", owner: "", due_date: "", priority: "medium" }); onAdded(); }
  };
  return (
    <form onSubmit={submit} className="grid grid-cols-12 gap-2 p-3 border-t border-slate-100">
      <input className="input col-span-12 md:col-span-6" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="New action item…" />
      <input className="input col-span-5 md:col-span-2" list="add-people" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} placeholder="Owner" />
      <datalist id="add-people">{people.map((p) => <option key={p} value={p} />)}</datalist>
      <input type="date" className="input col-span-5 md:col-span-3" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
      <button className="btn-secondary col-span-2 md:col-span-1 justify-center" disabled={busy || f.title.trim().length < 3} aria-label="Add item"><Plus className="w-4 h-4" /></button>
    </form>
  );
}

export default function MeetingDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const state = useLoad(() => Promise.all([api.get(`/meetings/${id}`), api.get("/people")]), [id]);
  const [openItem, setOpenItem] = useState(null);
  const [followUp, setFollowUp] = useState(false);
  const [editSummary, setEditSummary] = useState(null);
  const [showNotes, setShowNotes] = useState(false);
  const [linkMsg, setLinkMsg] = useState(null);
  const [run, busy] = useAction();

  const setMeeting = (m) => state.setData([m, state.data[1]]);
  const refresh = (m) => (m && m.id ? setMeeting(m) : state.reload());

  useEffect(() => {
    if (state.data && window.location.hash === "#conflicts") document.getElementById("conflicts")?.scrollIntoView({ behavior: "smooth" });
  }, [state.data]);

  return (
    <PageLoader state={state}>
      {([m, people]) => {
        const changeStatus = async (s) => { const r = await run(() => api.post(`/meetings/${m.id}/status`, { status: s }), `Marked ${s.replace("_", " ")}`); if (r) setMeeting(r); };
        const saveSummary = async () => { const r = await run(() => api.patch(`/meetings/${m.id}`, { summary: editSummary }), "Summary saved"); if (r) { setMeeting(r); setEditSummary(null); } };
        const toggle = async (p) => { const r = await run(() => api.patch(`/meetings/${m.id}/participants/${p.id}?attended=${!p.attended}`)); if (r) setMeeting(r); };
        const relink = async () => { const r = await run(() => api.post(`/meetings/${m.id}/link-knowledge`)); if (r) { setLinkMsg(r); state.reload(); } };
        const remove = async () => {
          if (!window.confirm?.("Delete this meeting and everything in it?")) return;
          const r = await run(() => api.del(`/meetings/${m.id}`), "Deleted");
          if (r !== undefined) nav("/meetings");
        };
        const openCount = m.items.filter((i) => !["done", "dropped"].includes(i.status)).length;

        return (
          <div className="space-y-5">
            <div>
              <Link to="/meetings" className="text-xs text-slate-500 hover:text-indigo-600 inline-flex items-center gap-1"><ArrowLeft className="w-3 h-3" />All meetings</Link>
              <div className="flex items-start justify-between gap-4 mt-2 flex-wrap">
                <div>
                  <h1 className="text-xl font-semibold text-slate-900">{m.title}</h1>
                  <div className="flex items-center gap-2 mt-1.5 text-sm text-slate-500 flex-wrap">
                    <KindBadge kind={m.kind} /><StatusBadge status={m.status} /><span>{fmtDateTime(m.scheduled_at)}</span>
                    {m.kind === "handover" && <span className="chip bg-violet-50 text-violet-700">{m.handover_from || "?"} <ArrowRight className="w-3 h-3" /> {m.handover_to}</span>}
                  </div>
                  <div className="flex gap-3 mt-2 text-xs">
                    {m.previous_id && <Link to={`/meetings/${m.previous_id}`} className="text-indigo-600 hover:underline inline-flex items-center gap-1"><ArrowLeft className="w-3 h-3" />Previous</Link>}
                    {m.next_id && <Link to={`/meetings/${m.next_id}`} className="text-indigo-600 hover:underline inline-flex items-center gap-1">Next<ArrowRight className="w-3 h-3" /></Link>}
                  </div>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {TRANSITIONS[m.status].map(([s, label]) => (
                    <button key={s} className={s === "cancelled" ? "btn-ghost" : "btn-secondary"} disabled={busy} onClick={() => changeStatus(s)}>{label}</button>
                  ))}
                  <button className="btn-primary" onClick={() => setFollowUp(true)}><Plus className="w-4 h-4" />Follow-up{openCount ? ` (${openCount} carry over)` : ""}</button>
                  <button className="btn-ghost p-2" onClick={remove} aria-label="Delete"><Trash2 className="w-4 h-4" /></button>
                </div>
              </div>
            </div>

            <div className="grid lg:grid-cols-3 gap-5">
              <div className="lg:col-span-2 space-y-5">
                <CaptureRecap meeting={m} people={people} onSaved={(done, r) => (done ? setMeeting(r) : state.reload())} />

                <Card title="Summary" icon={FileText} actions={editSummary === null && <button className="btn-ghost p-1" onClick={() => setEditSummary(m.summary)} aria-label="Edit summary"><Pencil className="w-3.5 h-3.5" /></button>}>
                  <div className="p-4">
                    {editSummary !== null ? (
                      <div className="space-y-2">
                        <textarea className="input min-h-24" value={editSummary} onChange={(e) => setEditSummary(e.target.value)} />
                        <div className="flex gap-2"><button className="btn-primary" onClick={saveSummary} disabled={busy}>Save</button><button className="btn-ghost" onClick={() => setEditSummary(null)}>Cancel</button></div>
                      </div>
                    ) : m.summary ? (
                      <p className="text-sm leading-relaxed">{m.summary} <SourceTag source={m.summary_source} /></p>
                    ) : (
                      <p className="text-sm text-slate-400">No summary yet — paste notes above and generate a recap.</p>
                    )}
                  </div>
                </Card>

                <Decisions meeting={m} reload={refresh} />

                <Card title={`Action items (${openCount} open / ${m.items.length})`} icon={ListChecks}>
                  {m.items.length ? <ItemTable items={m.items} onOpen={setOpenItem} /> : <Empty icon={ListChecks} title="No action items" />}
                  <AddItem meetingId={m.id} people={people} onAdded={state.reload} />
                </Card>

                <section className="card">
                  <button className="w-full flex items-center justify-between px-4 py-3 section-title" onClick={() => setShowNotes(!showNotes)}>
                    <span className="flex items-center gap-2"><FileText className="w-4 h-4 text-slate-500" />Raw notes & sources ({m.notes.length})</span>
                    {showNotes ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  {showNotes && (
                    <div className="divide-y divide-slate-100 border-t border-slate-100">
                      {m.notes.map((n) => (
                        <div key={n.id} className="px-4 py-3">
                          <div className="text-xs text-slate-500 mb-1"><span className="chip bg-slate-100">{n.source}</span> {n.author} · {fmtDateTime(n.created_at)}</div>
                          <pre className="text-xs whitespace-pre-wrap font-mono text-slate-700">{n.content}</pre>
                        </div>
                      ))}
                      {!m.notes.length && <Empty title="No raw notes saved" />}
                    </div>
                  )}
                </section>
              </div>

              <div className="space-y-5">
                <BriefPanel meeting={m} />

                <Card title={`Participants (${m.participants.length})`} icon={UserCheck}>
                  <div className="divide-y divide-slate-100">
                    {m.participants.map((p) => (
                      <div key={p.id} className="flex items-center justify-between px-4 py-2">
                        <div>
                          <div className={`text-sm ${p.attended ? "" : "text-slate-400"}`}>{p.name}</div>
                          {p.role && <div className="text-[11px] text-slate-400">{p.role}</div>}
                        </div>
                        <button className={`chip ${p.attended ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`} onClick={() => toggle(p)} title="Toggle attendance">
                          {p.attended ? <><UserCheck className="w-3 h-3" />attended</> : <><UserX className="w-3 h-3" />absent</>}
                        </button>
                      </div>
                    ))}
                    {!m.participants.length && <Empty title="No participants" />}
                  </div>
                </Card>

                <Card title="Related knowledge" icon={Link2} actions={<button className="btn-ghost p-1" onClick={relink} disabled={busy} title="Find related documents & meetings with AI">{busy ? <Spinner className="w-3.5 h-3.5" /> : <RefreshCw className="w-3.5 h-3.5" />}</button>}>
                  <div className="p-2">
                    {linkMsg && <div className="p-2"><AIBanner status={linkMsg.ai_status} message={linkMsg.ai_message} /></div>}
                    {m.links.map((l) => (
                      <Link key={l.id} to={l.doc_id ? `/knowledge?doc=${l.doc_id}` : `/meetings/${l.linked_meeting_id}`} className="block rounded-lg px-2 py-2 hover:bg-slate-50">
                        <div className="text-sm font-medium flex items-center gap-1.5">
                          {l.doc_id ? <BookOpen className="w-3.5 h-3.5 text-indigo-500" /> : <FileText className="w-3.5 h-3.5 text-slate-400" />}
                          {l.title}
                          <span className="text-[10px] text-slate-400 ml-auto">{Math.round(l.score * 100)}%</span>
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5 ml-5">{l.reason}</div>
                      </Link>
                    ))}
                    {!m.links.length && <Empty icon={Link2} title="No links yet" hint="Saved recaps are linked automatically, or press refresh." />}
                  </div>
                </Card>

                {m.agenda && (
                  <Card title="Agenda" icon={ListChecks}>
                    <pre className="p-4 text-sm whitespace-pre-wrap font-sans text-slate-700">{m.agenda}</pre>
                  </Card>
                )}
                <div className="text-[11px] text-slate-400 px-1">Created {fmtDate(m.created_at)} · updated {fmtDateTime(m.updated_at)}</div>
              </div>
            </div>

            <ItemDrawer itemId={openItem} onClose={() => setOpenItem(null)} onChanged={state.reload} people={people} />
            <NewMeetingModal open={followUp} onClose={() => setFollowUp(false)} people={people} previous={m} />
          </div>
        );
      }}
    </PageLoader>
  );
}
