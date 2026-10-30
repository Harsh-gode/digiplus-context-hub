import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BookOpen, CheckSquare, FileText, Gavel, MessageCircleQuestion, Sparkles } from "lucide-react";
import { api } from "../api";
import { AIBanner, Markdown, Spinner, useAction } from "../components/ui";

const EXAMPLES = [
  "Where should the analytics dashboard be hosted?",
  "What did Rahul hand over to Sneha?",
  "What's blocking M2?",
  "What is our P1 incident SLA?",
];
const ICON = { doc: BookOpen, meeting: FileText, item: CheckSquare, decision: Gavel };
const href = (s) => (s.kind === "doc" ? `/knowledge?doc=${s.id}` : s.kind === "meeting" ? `/meetings/${s.id}` : `/items`);

export default function Ask() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]);
  const [run, busy] = useAction();
  const [params] = useSearchParams();
  const asked = useRef(false);

  const ask = async (q) => {
    const text = (q ?? question).trim();
    if (text.length < 3) return;
    const r = await run(() => api.post("/ask", { question: text }));
    if (r) { setHistory((h) => [{ q: text, ...r }, ...h]); setQuestion(""); }
  };

  // A question passed in the URL (from the dashboard or the command palette) is asked straight away.
  useEffect(() => {
    const q = params.get("q");
    if (q && !asked.current) { asked.current = true; ask(q); }
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-5 max-w-3xl animate-fade-up">
      <div>
        <div className="eyebrow mb-2"><span className="w-6 h-px bg-brand-600" />AI assistant</div>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Ask the team <span className="text-gradient">memory</span></h1>
        <p className="text-sm text-slate-500">Answers come only from your meetings, decisions, action items and documents — with sources.</p>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="card p-3 flex gap-2">
        <MessageCircleQuestion className="w-5 h-5 text-slate-400 mt-1.5 shrink-0" />
        <input className="input border-0 focus:ring-0 px-1" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask anything about past work…" autoFocus />
        <button className="btn-primary shrink-0" disabled={busy || question.trim().length < 3}>{busy ? <Spinner /> : <Sparkles className="w-4 h-4" />}Ask</button>
      </form>
      {!history.length && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((e) => <button key={e} className="chip bg-white border border-slate-200 text-slate-600 hover:border-brand-300 py-1 px-3" onClick={() => ask(e)}>{e}</button>)}
        </div>
      )}
      {history.map((h, i) => (
        <div key={i} className="card p-4 space-y-3">
          <div className="text-sm font-medium text-slate-900">{h.q}</div>
          <AIBanner status={h.ai_status} message={h.ai_message} />
          <Markdown text={h.answer} />
          {h.sources.length > 0 && (
            <div className="border-t border-slate-100 pt-3 flex flex-wrap gap-2">
              {h.sources.map((s) => {
                const Icon = ICON[s.kind] || FileText;
                return (
                  <Link key={s.key} to={href(s)} className="chip bg-slate-50 border border-slate-200 text-slate-600 hover:border-brand-300 py-1 px-2.5">
                    <Icon className="w-3 h-3" /><span className="text-slate-400">[{s.key}]</span> {s.title}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
