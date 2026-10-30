import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { Plus, Search, Sparkles } from "lucide-react";
import "./index.css";
import { api } from "./api";
import { ToastProvider, useLoad } from "./components/ui";
import CommandPalette from "./components/CommandPalette";
import NewMeetingModal from "./components/NewMeetingModal";
import Dashboard from "./pages/Dashboard";
import Meetings from "./pages/Meetings";
import MeetingDetail from "./pages/MeetingDetail";
import Items from "./pages/Items";
import Knowledge from "./pages/Knowledge";
import Ask from "./pages/Ask";
import Followups from "./pages/Followups";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/meetings", label: "Meetings" },
  { to: "/items", label: "Board" },
  { to: "/followups", label: "Follow-ups" },
  { to: "/knowledge", label: "Knowledge" },
  { to: "/ask", label: "Ask AI" },
];

function Wordmark() {
  return (
    <NavLink to="/" className="flex items-center gap-2.5 shrink-0" aria-label="DigiPlus Context Hub home">
      <span className="flex items-baseline text-[22px] font-semibold tracking-tight leading-none">
        <span className="text-coral">Digi</span><span className="text-violet">Plus</span>
      </span>
      <span className="rounded-md bg-emerald-600 text-white text-[11px] font-semibold px-1.5 py-1 leading-none">IT</span>
      <span className="hidden lg:block h-5 w-px bg-slate-200" />
      <span className="hidden lg:block text-sm font-medium text-slate-500">Context Hub</span>
    </NavLink>
  );
}

function AIStatus() {
  const { data } = useLoad(() => api.get("/health"));
  if (!data) return null;
  const on = data.ai.enabled;
  return (
    <span title={on ? `${data.ai.provider} · ${data.ai.model}` : "No AI key configured — rule-based fallbacks active"}
      className={`hidden md:inline-flex chip py-1 ${on ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${on ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
      <Sparkles className="w-3 h-3" />{on ? `AI · ${data.ai.provider}` : "AI offline"}
    </span>
  );
}

function Header() {
  const [newOpen, setNewOpen] = useState(false);
  const people = useLoad(() => api.get("/people"));
  const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);
  return (
    <header className="sticky top-0 z-30 bg-white/90 backdrop-blur border-b border-slate-200/80">
      <div className="max-w-7xl mx-auto px-4 md:px-8 h-16 flex items-center gap-6">
        <Wordmark />
        <nav className="hidden md:flex items-center gap-1 ml-auto">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `nav-underline px-3 py-2 text-[15px] transition ${isActive ? "active text-slate-900 font-medium" : "text-slate-500 hover:text-slate-900"}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-2 ml-auto md:ml-2">
          <button onClick={() => window.dispatchEvent(new Event("open-palette"))}
            className="btn-secondary py-1.5 text-slate-500" aria-label="Search (Command K)">
            <Search className="w-4 h-4" /><span className="hidden lg:inline">Search</span>
            <kbd className="hidden lg:inline text-[10px] border border-slate-200 rounded px-1">{isMac ? "⌘K" : "Ctrl K"}</kbd>
          </button>
          <AIStatus />
          <button className="btn-primary" onClick={() => setNewOpen(true)}><Plus className="w-4 h-4" /><span className="hidden sm:inline">New</span></button>
        </div>
      </div>
      <nav className="md:hidden flex gap-1 overflow-x-auto px-3 pb-2">
        {NAV.map(({ to, label, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `px-3 py-1.5 rounded-lg text-sm whitespace-nowrap ${isActive ? "bg-brand-50 text-brand-700 font-medium" : "text-slate-500"}`}>{label}</NavLink>
        ))}
      </nav>
      <NewMeetingModal open={newOpen} onClose={() => setNewOpen(false)} people={people.data || []} />
    </header>
  );
}

function Layout() {
  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-7xl mx-auto px-4 md:px-8 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/meetings" element={<Meetings />} />
          <Route path="/meetings/:id" element={<MeetingDetail />} />
          <Route path="/items" element={<Items />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/followups" element={<Followups />} />
          <Route path="*" element={<div className="card p-8 text-center">Page not found</div>} />
        </Routes>
      </main>
      <footer className="max-w-7xl mx-auto px-4 md:px-8 pb-8 text-xs text-slate-400 flex justify-between">
        <span>DigiPlus Context Hub · capture decisions, hand over context, close the loop</span>
        <span className="hidden sm:inline">Press ⌘K anywhere</span>
      </footer>
      <CommandPalette />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <Layout />
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>
);
