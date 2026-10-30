import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BookOpen, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { api, fmtDate } from "../api";
import { Empty, Field, Modal, PageLoader, useAction, useLoad } from "../components/ui";

const TYPES = ["document", "policy", "runbook", "spec", "note"];

function DocForm({ doc, onDone }) {
  const [f, setF] = useState(doc ? { ...doc, tags: doc.tags.join(", ") } : { title: "", content: "", tags: "", doc_type: "document" });
  const [run, busy] = useAction();
  const submit = async (e) => {
    e.preventDefault();
    const body = { title: f.title, content: f.content, doc_type: f.doc_type, tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean) };
    const r = await run(() => (doc ? api.put(`/knowledge/${doc.id}`, body) : api.post("/knowledge", body)), doc ? "Document updated" : "Document added");
    if (r) onDone(r);
  };
  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="Title"><input className="input" required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Type"><select className="input" value={f.doc_type} onChange={(e) => setF({ ...f, doc_type: e.target.value })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Tags (comma separated)"><input className="input" value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></Field>
      </div>
      <Field label="Content" hint="Policies and standards here are what decisions get checked against."><textarea className="input min-h-48" required minLength={10} value={f.content} onChange={(e) => setF({ ...f, content: e.target.value })} /></Field>
      <div className="flex justify-end"><button className="btn-primary" disabled={busy}>Save</button></div>
    </form>
  );
}

export default function Knowledge() {
  const [q, setQ] = useState("");
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("doc");
  const state = useLoad(() => api.get(`/knowledge${q ? `?q=${encodeURIComponent(q)}` : ""}`), [q]);
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null); // null | "new" | doc
  const [run] = useAction();

  useEffect(() => {
    if (selectedId) api.get(`/knowledge/${selectedId}`).then(setSelected).catch(() => setSelected(null));
    else setSelected(null);
  }, [selectedId]);

  const del = async (doc) => {
    if (!window.confirm?.(`Delete “${doc.title}”?`)) return;
    const r = await run(() => api.del(`/knowledge/${doc.id}`), "Deleted");
    if (r !== undefined) { setParams({}); state.reload(); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Knowledge base</h1>
          <p className="text-sm text-slate-500">Team documents, policies and runbooks. Meetings are linked to these automatically.</p>
        </div>
        <button className="btn-primary" onClick={() => setEditing("new")}><Plus className="w-4 h-4" />Add document</button>
      </div>
      <div className="relative">
        <Search className="w-4 h-4 absolute left-2.5 top-2 text-slate-400" />
        <input className="input pl-8" placeholder="Search documents…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <PageLoader state={state}>
        {(docs) => (
          <div className="grid md:grid-cols-5 gap-4">
            <div className="md:col-span-2 card divide-y divide-slate-100 h-fit">
              {docs.map((d) => (
                <button key={d.id} onClick={() => setParams({ doc: d.id })} className={`w-full text-left px-4 py-3 hover:bg-slate-50 ${String(d.id) === selectedId ? "bg-indigo-50/60" : ""}`}>
                  <div className="text-sm font-medium">{d.title}</div>
                  <div className="flex gap-1 mt-1 flex-wrap">
                    <span className="chip bg-slate-100 text-slate-600">{d.doc_type}</span>
                    {d.tags.slice(0, 3).map((t) => <span key={t} className="chip bg-slate-50 text-slate-400">#{t}</span>)}
                  </div>
                </button>
              ))}
              {!docs.length && <Empty icon={BookOpen} title="No documents" />}
            </div>
            <div className="md:col-span-3">
              {selected ? (
                <div className="card p-5">
                  <div className="flex justify-between gap-2">
                    <h2 className="font-semibold text-lg">{selected.title}</h2>
                    <div className="flex gap-1">
                      <button className="btn-ghost p-1.5" onClick={() => setEditing(selected)} aria-label="Edit"><Pencil className="w-4 h-4" /></button>
                      <button className="btn-ghost p-1.5" onClick={() => del(selected)} aria-label="Delete"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">{selected.doc_type} · updated {fmtDate(selected.updated_at)}</div>
                  <p className="text-sm leading-relaxed mt-4 whitespace-pre-wrap">{selected.content}</p>
                  {selected.linked_meetings?.length > 0 && (
                    <div className="mt-5 border-t border-slate-100 pt-4">
                      <div className="section-title mb-2">Referenced by</div>
                      {selected.linked_meetings.map((m, i) => (
                        <Link key={i} to={`/meetings/${m.id}`} className="block py-1.5 text-sm">
                          <span className="text-indigo-600 hover:underline">{m.title}</span>
                          <span className="block text-xs text-slate-500">{m.reason}</span>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="card"><Empty icon={BookOpen} title="Select a document" /></div>
              )}
            </div>
          </div>
        )}
      </PageLoader>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? "Add document" : "Edit document"} wide>
        {editing && <DocForm doc={editing === "new" ? null : editing} onDone={(d) => { setEditing(null); state.reload(); setParams({ doc: d.id }); api.get(`/knowledge/${d.id}`).then(setSelected); }} />}
      </Modal>
    </div>
  );
}
