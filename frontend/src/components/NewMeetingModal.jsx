import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, FileUp, Plus, Trash2, X } from "lucide-react";
import { api } from "../api";
import { Field, Modal, useAction, useToast } from "./ui";

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
  const [transcript, setTranscript] = useState(null);
  const [fileError, setFileError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);
  const pickTranscript = (file) => {
    if (!file) return;
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (![".vtt", ".docx", ".txt"].includes(ext)) return setFileError("Use a Teams transcript: .vtt, .docx or .txt");
    if (file.size > 10 * 1024 * 1024) return setFileError("File is larger than 10 MB");
    setFileError("");
    setTranscript(file);
  };
  const toast = useToast();
  useEffect(() => { if (open) { setF(blank()); setTranscript(null); setFileError(""); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if (!m) return;
    let draft = null;
    if (transcript) {
      // Meeting is saved first; a transcript problem shouldn't lose the meeting.
      draft = await run(() => api.upload(`/meetings/${m.id}/transcript`, transcript));
      if (draft?.speakers_added?.length) toast(`Added ${draft.speakers_added.length} speakers from the transcript`);
    }
    onClose();
    nav(`/meetings/${m.id}`, { state: draft ? { draft } : null });
  };

  return (
    <Modal open={open} onClose={onClose} title={previous ? "Schedule follow-up" : "New meeting or handover"}>
      <form onSubmit={submit} className="space-y-4">
        {!previous && (
          <div className="grid grid-cols-2 gap-2">
            {["meeting", "handover"].map((k) => (
              <button type="button" key={k} onClick={() => setF({ ...f, kind: k })}
                className={`rounded-lg border px-3 py-2 text-left text-sm ${f.kind === k ? "border-brand-500 bg-brand-50" : "border-slate-200"}`}>
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
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="label mb-0">Agenda</span>
            <button type="button" className="text-xs font-medium text-brand-600 hover:text-brand-700 flex items-center gap-1" onClick={() => fileRef.current?.click()}>
              <FileUp className="w-3.5 h-3.5" />Upload Teams transcript
            </button>
            <input ref={fileRef} type="file" accept=".vtt,.docx,.txt" className="hidden" onChange={(e) => { pickTranscript(e.target.files?.[0]); e.target.value = ""; }} />
          </div>
          <div className={`rounded-xl transition ${dragOver ? "ring-4 ring-brand-100" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); pickTranscript(e.dataTransfer.files?.[0]); }}>
            <textarea className="input min-h-20" value={f.agenda} onChange={(e) => setF({ ...f, agenda: e.target.value })}
              placeholder="Type the agenda, or drop a Teams transcript (.vtt / .docx / .txt) here" />
          </div>
          {fileError && <div className="text-xs text-red-600 mt-1">{fileError}</div>}
          {transcript && (
            <div className="mt-2 flex items-center gap-2 rounded-xl border border-brand-200 bg-brand-50/60 px-3 py-2 text-sm animate-pop">
              <FileText className="w-4 h-4 text-brand-600 shrink-0" />
              <span className="truncate flex-1 font-medium">{transcript.name}</span>
              <span className="text-xs text-slate-500 hidden sm:inline">AI drafts the recap after you create</span>
              <button type="button" className="btn-ghost p-1" onClick={() => setTranscript(null)} aria-label="Remove transcript"><X className="w-4 h-4" /></button>
            </div>
          )}
        </div>
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
          <button className="btn-primary" disabled={busy}>{busy && transcript ? "Reading transcript…" : previous ? "Create follow-up" : transcript ? "Create & draft recap" : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}
