import { useRef, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";

/**
 * Click-or-drag file picker. `accept` is a comma list like ".pdf,.docx".
 * Checks extension and size in the browser too, so users get instant feedback (the server checks again).
 */
export default function DropZone({ accept, onFile, busy, title, hint, maxMb = 10, compact = false }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState("");

  const pick = (file) => {
    if (!file) return;
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!accept.split(",").includes(ext)) return setError(`That file type isn't supported. Use ${accept.replaceAll(",", ", ")}.`);
    if (file.size > maxMb * 1024 * 1024) return setError(`File is larger than ${maxMb} MB.`);
    setError("");
    onFile(file);
  };

  return (
    <div>
      <button type="button" disabled={busy}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]); }}
        className={`w-full rounded-2xl border-2 border-dashed text-center transition ${compact ? "px-4 py-4" : "px-6 py-8"}
          ${over ? "border-brand-500 bg-brand-50" : "border-slate-300 hover:border-brand-400 hover:bg-brand-50/40"} ${busy ? "opacity-70 cursor-wait" : ""}`}>
        <span className={`mx-auto grid place-items-center rounded-full bg-brand-gradient text-white ${compact ? "w-9 h-9 mb-1.5" : "w-11 h-11 mb-2"}`}>
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <FileUp className="w-5 h-5" />}
        </span>
        <span className="block text-sm font-medium text-slate-800">{busy ? "Reading the file…" : title}</span>
        <span className="block text-xs text-slate-500 mt-0.5">{hint}</span>
      </button>
      <input ref={input} type="file" accept={accept} className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      {error && <div className="text-xs text-red-600 mt-1.5">{error}</div>}
    </div>
  );
}
