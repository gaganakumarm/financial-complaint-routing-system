import { formatRole } from "../features/auth/roles";
import { useAuth } from "../features/auth/useAuth";

export function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  return <section><div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-8"><p className="text-sm font-semibold text-teal-700 dark:text-teal-400">{formatRole(user.role_name)} workspace</p><h2 className="mt-2 text-2xl font-semibold">Welcome, {user.full_name}</h2><p className="mt-3 max-w-2xl text-slate-600 dark:text-slate-400">Your operational modules will appear here as they are enabled. Use the navigation to preview the available workspace areas.</p></div></section>;
}
