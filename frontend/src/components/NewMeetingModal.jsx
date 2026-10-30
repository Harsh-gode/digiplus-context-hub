import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { Field, Modal, useAction } from "./ui";

const localNow = () => {
  const d = new Date();
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

// Create a meeting / handover, or a follow-up of an existing one (previous = meeting detail object).
export default function NewMeetingModal({ open, onClose, people = [], previous = null, defaultKind = "meeting" }) {
  const nav = useNavigate();
  const [run, busy] = useAction();
  const blank = () => ({
    kind: previous?.kind || defaultKind,
    title: previous?.title || "",
    scheduled_at: localNow(),
    agenda: previous ? "1. Carried-over items\n2. " : "",
    participants: previous ? previous.participants.map((p) => p.name) : [],
    carry_forward_open_items: true,
    handover_from: "",
    handover_to: "",
  });
  const [f, setF] = useState(blank);
  const [newName, setNewName] = useState("");
  useEffect(() => { if (open) setF(blank()); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const addPerson = (name) => {
    const n = name.trim();
    if (n && !f.participants.some((p) => p.toLowerCase() === n.toLowerCase())) setF({ ...f, participants: [...f.participants, n] });
    setNewName("");
  };

  const submit = async (e) => {
    e.preventDefault();
    const participants = [...f.participants];
    if (f.kind === "handover") [f.handover_from, f.handover_to].forEach((n) => n.trim() && !participants.includes(n.trim()) && participants.push(n.trim()));
    const body = { ...f, scheduled_at: new Date(f.scheduled_at).toISOString(), participants: participants.map((name) => ({ name })) };
    const path = previous ? `/meetings/${previous.id}/follow-up` : "/meetings";
    const m = await run(() => api.post(path, body), previous ? "Follow-up created — open items carried forward" : "Created");
    if (m) { onClose(); nav(`/meetings/${m.id}`); }
  };

  return (
    <Modal open={open} onClose={onClose} title={previous ? "Schedule follow-up" : "New meeting or handover"}>
      <form onSubmit={submit} className="space-y-4">
        {!previous && (
          <div className="grid grid-cols-2 gap-2">
            {["meeting", "handover"].map((k) => (
              <button type="button" key={k} onClick={() => setF({ ...f, kind: k })}
                className={`rounded-lg border px-3 py-2 text-left text-sm ${f.kind === k ? "border-indigo-500 bg-indigo-50" : "border-slate-200"}`}>
                <div className="font-medium capitalize">{k}</div>
                <div className="text-xs text-slate-500">{k === "meeting" ? "Agenda, notes, decisions, actions" : "Transfer work when someone leaves or rotates"}</div>
              </button>
            ))}
          </div>
        )}
        <Field label="Title"><input className="input" required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={f.kind === "handover" ? "Handover: Rahul → Sneha (payments)" : "Weekly delivery sync"} /></Field>
        <Field label="Date & time"><input type="datetime-local" className="input" required value={f.scheduled_at} onChange={(e) => setF({ ...f, scheduled_at: e.target.value })} /></Field>
        {f.kind === "handover" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Handing over"><input className="input" list="np-people" value={f.handover_from} onChange={(e) => setF({ ...f, handover_from: e.target.value })} /></Field>
            <Field label="Taking over *"><input className="input" list="np-people" required value={f.handover_to} onChange={(e) => setF({ ...f, handover_to: e.target.value })} /></Field>
          </div>
        )}
        <Field label="Agenda"><textarea className="input min-h-20" value={f.agenda} onChange={(e) => setF({ ...f, agenda: e.target.value })} /></Field>
        <div>
          <span className="label">Participants</span>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {f.participants.map((p) => (
              <span key={p} className="chip bg-slate-100 text-slate-700">{p}
                <button type="button" onClick={() => setF({ ...f, participants: f.participants.filter((x) => x !== p) })} aria-label={`Remove ${p}`}><Trash2 className="w-3 h-3" /></button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input className="input" list="np-people" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Add a person"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addPerson(newName); } }} />
            <button type="button" className="btn-secondary" onClick={() => addPerson(newName)}><Plus className="w-4 h-4" /></button>
          </div>
          <datalist id="np-people">{people.map((p) => <option key={p} value={p} />)}</datalist>
        </div>
        {previous && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.carry_forward_open_items} onChange={(e) => setF({ ...f, carry_forward_open_items: e.target.checked })} />
            Carry forward all open action items (history is kept)
          </label>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy}>{previous ? "Create follow-up" : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}
