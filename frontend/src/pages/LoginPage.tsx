import { Navigate } from "react-router-dom";
import { LoadingState } from "../components/common/States";
import { LoginForm } from "../features/auth/LoginForm";
import { useAuth } from "../features/auth/useAuth";

export function LoginPage() {
  const { user, isRestoring } = useAuth();
  if (isRestoring) return <LoadingState label="Restoring your session" fullScreen />;
  if (user) return <Navigate to="/" replace />;
  return <main className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(420px,560px)]">
    <section className="hidden bg-slate-950 p-12 text-slate-100 lg:flex lg:flex-col lg:justify-between"><div><p className="text-sm font-semibold uppercase tracking-widest text-teal-400">Financial operations</p><h1 className="mt-5 max-w-xl text-4xl font-semibold leading-tight">Complaint routing and model governance in one controlled workspace.</h1><p className="mt-5 max-w-lg text-slate-300">Secure access for customers, reviewers, and administrators.</p></div><p className="text-sm text-slate-500">Financial Complaint Routing System</p></section>
    <section className="flex items-center justify-center bg-white px-6 py-12 dark:bg-slate-900"><div className="w-full max-w-sm"><div className="mb-8"><p className="text-sm font-semibold text-teal-700 dark:text-teal-400">FCRS</p><h2 className="mt-2 text-2xl font-semibold">Sign in to your workspace</h2><p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Use your authorized account credentials.</p></div><LoginForm /></div></section>
  </main>;
}
