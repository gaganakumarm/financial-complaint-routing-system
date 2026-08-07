import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { formatRole } from "../../features/auth/roles";
import { useAuth } from "../../features/auth/useAuth";
import { useTheme } from "../../hooks/useTheme";
import { getNavigation } from "./navigation";

const titles: Record<string, string> = { "/": "Dashboard", "/my-complaints": "My Complaints", "/review-queue": "Review Queue", "/complaints": "Complaints", "/datasets": "Datasets", "/benchmarks": "Benchmarks", "/comparisons": "Comparisons", "/model-promotions": "Model Promotions", "/deployment-candidates": "Deployment Candidates", "/deployment-history": "Deployment History" };

export function AppShell() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  if (!user) return null;
  const links = getNavigation(user.role_name);
  return <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
    {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden" onClick={() => setMobileOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-slate-950 text-slate-100 transition-transform dark:border-slate-800 ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
      <div className="border-b border-slate-800 px-5 py-5"><p className="text-xs font-semibold uppercase tracking-widest text-teal-400">FCRS</p><p className="mt-1 font-semibold">Financial Complaint Routing</p></div>
      <nav aria-label="Primary navigation" className="flex-1 space-y-1 overflow-y-auto p-3">{links.map((item) => <NavLink key={item.path} to={item.path} end={item.path === "/"} onClick={() => setMobileOpen(false)} className={({ isActive }) => `block rounded-md px-3 py-2.5 text-sm ${isActive ? "bg-teal-700 font-semibold text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}>{item.label}</NavLink>)}</nav>
      <div className="border-t border-slate-800 p-4 text-xs text-slate-400">Governance workspace</div>
    </aside>
    <div className="lg:pl-64">
      <header className="sticky top-0 z-20 flex min-h-16 items-center justify-between border-b border-slate-200 bg-white px-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:px-6">
        <div className="flex items-center gap-3"><button aria-label="Open navigation" className="rounded p-2 text-slate-600 lg:hidden" onClick={() => setMobileOpen(true)}>☰</button><h1 className="font-semibold">{titles[pathname] ?? "Workspace"}</h1></div>
        <div className="flex items-center gap-3"><select aria-label="Color theme" value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)} className="rounded-md border border-slate-300 bg-transparent px-2 py-1.5 text-xs dark:border-slate-700"><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select><div className="hidden text-right sm:block"><p className="text-sm font-medium">{user.full_name}</p><p className="text-xs text-slate-500 dark:text-slate-400">{user.email} · {formatRole(user.role_name)}</p></div><button onClick={logout} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">Log out</button></div>
      </header>
      <main className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8"><Outlet /></main>
    </div>
  </div>;
}
