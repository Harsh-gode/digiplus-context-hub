import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { BookOpen, CheckSquare, LayoutDashboard, MessageCircleQuestion, Sparkles, Users } from "lucide-react";
import "./index.css";
import { api } from "./api";
import { ToastProvider, useLoad } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import Meetings from "./pages/Meetings";
import MeetingDetail from "./pages/MeetingDetail";
import Items from "./pages/Items";
import Knowledge from "./pages/Knowledge";
import Ask from "./pages/Ask";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/meetings", label: "Meetings & handovers", icon: Users },
  { to: "/items", label: "Action items", icon: CheckSquare },
  { to: "/knowledge", label: "Knowledge base", icon: BookOpen },
  { to: "/ask", label: "Ask team memory", icon: MessageCircleQuestion },
];

function AIStatus() {
  const { data } = useLoad(() => api.get("/health"));
  if (!data) return null;
  const on = data.ai.enabled;
  return (
    <div className={`mx-3 mb-3 rounded-lg px-3 py-2 text-xs ${on ? "bg-indigo-500/20 text-indigo-100" : "bg-amber-400/15 text-amber-200"}`}>
      <div className="flex items-center gap-1.5 font-medium"><Sparkles className="w-3.5 h-3.5" />{on ? "AI connected" : "AI offline"}</div>
      <div className="opacity-80 mt-0.5">{on ? `${data.ai.provider} · ${data.ai.model}` : "Rule-based fallbacks active"}</div>
    </div>
  );
}

function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-60 shrink-0 bg-slate-900 text-slate-300 flex flex-col sticky top-0 h-screen max-md:hidden">
        <div className="px-5 py-5 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 grid place-items-center text-white font-bold text-sm">D+</div>
          <div>
            <div className="text-white font-semibold text-sm leading-tight">Context Hub</div>
            <div className="text-[11px] text-slate-400">DigiPlus</div>
          </div>
        </div>
        <nav className="px-3 flex-1 space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition ${isActive ? "bg-slate-800 text-white" : "hover:bg-slate-800/60 hover:text-white"}`}>
              <Icon className="w-4 h-4" />{label}
            </NavLink>
          ))}
        </nav>
        <AIStatus />
      </aside>
      <div className="flex-1 min-w-0">
        <nav className="md:hidden flex gap-1 overflow-x-auto bg-slate-900 px-2 py-2">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `px-3 py-1.5 rounded-md text-xs whitespace-nowrap ${isActive ? "bg-slate-700 text-white" : "text-slate-300"}`}>{label}</NavLink>
          ))}
        </nav>
        <main className="max-w-6xl mx-auto px-4 md:px-8 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/meetings" element={<Meetings />} />
            <Route path="/meetings/:id" element={<MeetingDetail />} />
            <Route path="/items" element={<Items />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="*" element={<div className="card p-8 text-center">Page not found</div>} />
          </Routes>
        </main>
      </div>
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
