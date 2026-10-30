import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BookOpen, ClipboardPaste, Eye, FileText, FileUp, Pencil, Plus, Search, Sparkles, Trash2, X } from "lucide-react";
import { api, fmtDate } from "../api";
import { AIBanner, Empty, Field, Modal, PageLoader, useAction, useLoad } from "../components/ui";
import DropZone from "../components/DropZone";

const TYPES = ["document", "policy", "runbook", "spec", "note"];

function TagEditor({ tags, setTags }) {
  const [text, setText] = useState("");
  const add = () => {
    const t = text.trim().toLowerCase().replace(/\s+/g, "-");
    if (t && !tags.includes(t)) setTags([...tags, t]);
    setText("");
  };
  return (
    <div className="input flex flex-wrap gap-1.5 items-center min-h-10 py-1.5">
      {tags.map((t) => (
        <span key={t} className="chip bg-brand-50 text-brand-700">#{t}
          <button type="button" onClick={() => setTags(tags.filter((x) => x !== t))} aria-label={`Remove ${t}`}><X className="w-3 h-3" /></button>
        </span>
      ))}
      <input className="flex-1 min-w-24 outline-none text-sm bg-transparent" value={text} placeholder={tags.length ? "Add tag" : "Add tags…"}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} onBlur={add} />
    </div>
  );
}

function DocForm({ doc, onDone }) {
  const editing = !!doc;
  const [f, setF] = useState(doc ? { title: doc.title, content: doc.content, tags: doc.tags, doc_type: doc.doc_type } : { title: "", content: "", tags: [], doc_type: "document" });
  const [mode, setMode] = useState(editing ? "paste" : "upload"); // upload | paste
  const [analysis, setAnalysis] = useState(null);
  const [showText, setShowText] = useState(false);
  const [run, busy] = useAction();
  const [reading, setReading] = useState(false);

  const onFile = async (file) => {
    setReading(true);
    const r = await run(() => api.upload("/knowledge/analyze", file));
    setReading(false);
    if (r) {
      setAnalysis(r);
      setF({ title: r.title, content: r.content, tags: r.tags, doc_type: r.doc_type });
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    const body = { title: f.title, content: f.content, doc_type: f.doc_type, tags: f.tags };
    const r = await run(() => (editing ? api.put(`/knowledge/${doc.id}`, body) : api.post("/knowledge", body)), editing ? "Document updated" : "Document added to the knowledge base");
    if (r) onDone(r);
  };

  const showFields = editing || mode === "paste" || analysis;

  return (
    <form onSubmit={submit} className="space-y-4">
      {!editing && !analysis && (
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 w-fit">
          {[["upload", "Upload a file", FileUp], ["paste", "Paste text", ClipboardPaste]].map(([v, label, Icon]) => (
            <button key={v} type="button" onClick={() => setMode(v)}
              className={`flex items-center gap-1.5 px-3 py-1 text-sm rounded-md transition ${mode === v ? "bg-white shadow-sm text-slate-900 font-medium" : "text-slate-500"}`}>
              <Icon className="w-4 h-4" />{label}
            </button>
          ))}
        </div>
      )}

      {!editing && mode === "upload" && !analysis && (
        <DropZone accept=".pdf,.docx,.txt,.md" onFile={onFile} busy={reading}
          title="Drop a PDF, Word or text file — or click to choose"
          hint="AI reads it and suggests the title, type and tags. Up to 10 MB." />
      )}

      {analysis && (
        <div className="rounded-xl border border-brand-100 bg-brand-50/50 p-3.5 space-y-2 animate-pop">
          <div className="flex items-center gap-2 text-sm">
            <FileText className="w-4 h-4 text-brand-600" />
            <span className="font-medium truncate">{analysis.filename}</span>
            <span className="text-xs text-slate-500 shrink-0">{analysis.pages ? `${analysis.pages} page${analysis.pages > 1 ? "s" : ""} · ` : ""}{analysis.chars.toLocaleString()} characters</span>
            <button type="button" className="btn-ghost text-xs ml-auto py-1" onClick={() => { setAnalysis(null); setF({ title: "", content: "", tags: [], doc_type: "document" }); }}>Choose another</button>
          </div>
          <AIBanner status={analysis.ai_status} message={analysis.ai_message} />
          {analysis.summary && <p className="text-sm text-slate-700"><Sparkles className="w-3.5 h-3.5 inline text-brand-600 mr-1" />{analysis.summary}</p>}
          {analysis.truncated && <p className="text-xs text-amber-700">This file is long; the first 100,000 characters were kept.</p>}
        </div>
      )}

      {showFields && (
        <>
          <Field label={analysis ? "Title (suggested by AI)" : "Title"}><input className="input" required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <div className="grid sm:grid-cols-3 gap-3">
            <Field label="Type"><select className="input" value={f.doc_type} onChange={(e) => setF({ ...f, doc_type: e.target.value })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
            <div className="sm:col-span-2"><span className="label">{analysis ? "Tags (suggested by AI — edit freely)" : "Tags"}</span><TagEditor tags={f.tags} setTags={(tags) => setF({ ...f, tags })} /></div>
          </div>
          {analysis && !showText ? (
            <button type="button" className="btn-ghost text-xs -ml-2" onClick={() => setShowText(true)}><Eye className="w-3.5 h-3.5" />View or edit the extracted text</button>
          ) : (
            <Field label={analysis ? "Extracted text" : "Content"} hint="Policies and standards here are what decisions get checked against.">
              <textarea className="input min-h-48 font-mono text-[13px]" required minLength={10} value={f.content} onChange={(e) => setF({ ...f, content: e.target.value })} />
            </Field>
          )}
          <div className="flex justify-end"><button className="btn-primary" disabled={busy || f.content.trim().length < 10 || f.title.trim().length < 3}>{editing ? "Save changes" : "Add to knowledge base"}</button></div>
        </>
      )}
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
    <div className="space-y-4 animate-fade-up">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="eyebrow mb-2"><span className="w-6 h-px bg-brand-600" />Team knowledge</div><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Knowledge <span className="text-gradient">base</span></h1>
          <p className="text-sm text-slate-500">Team documents, policies and runbooks. Meetings are linked to these automatically.</p>
        </div>
        <button className="btn-primary" onClick={() => setEditing("new")}><FileUp className="w-4 h-4" />Upload document</button>
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
                <button key={d.id} onClick={() => setParams({ doc: d.id })} className={`w-full text-left px-4 py-3 hover:bg-slate-50 ${String(d.id) === selectedId ? "bg-brand-50/60" : ""}`}>
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
                          <span className="text-brand-600 hover:underline">{m.title}</span>
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
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? "Add to the knowledge base" : "Edit document"} wide>
        {editing && <DocForm doc={editing === "new" ? null : editing} onDone={(d) => { setEditing(null); state.reload(); setParams({ doc: d.id }); api.get(`/knowledge/${d.id}`).then(setSelected); }} />}
      </Modal>
    </div>
  );
}
