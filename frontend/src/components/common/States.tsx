import { Link } from "react-router-dom";

export function LoadingState({ label = "Loading", fullScreen = false }: { label?: string; fullScreen?: boolean }) {
  return <div className={`grid place-items-center ${fullScreen ? "min-h-screen" : "min-h-48"}`} role="status"><div className="text-center"><div className="mx-auto mb-3 size-7 animate-spin rounded-full border-2 border-slate-300 border-t-teal-700" /><p className="text-sm text-slate-600 dark:text-slate-300">{label}…</p></div></div>;
}

export function ErrorState({ title = "Unable to load", message = "Please try again shortly.", onRetry }: { title?: string; message?: string; onRetry?: () => void }) {
  return <section role="alert" className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-900 dark:bg-red-950"><h2 className="font-semibold text-red-900 dark:text-red-100">{title}</h2><p className="mt-1 text-sm text-red-700 dark:text-red-200">{message}</p>{onRetry && <button className="mt-4 text-sm font-semibold text-red-800 underline" onClick={onRetry}>Try again</button>}</section>;
}

export function EmptyState({ title = "Nothing here yet", message = "Items will appear here when they are available." }: { title?: string; message?: string }) {
  return <section className="rounded-lg border border-dashed border-slate-300 p-10 text-center dark:border-slate-700"><h2 className="font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{message}</p></section>;
}

export function AccessDenied() {
  return <section className="mx-auto max-w-lg py-16 text-center"><p className="text-sm font-semibold text-teal-700">403</p><h1 className="mt-2 text-2xl font-semibold">Access denied</h1><p className="mt-2 text-slate-600 dark:text-slate-400">Your account does not have permission to view this page.</p><Link to="/" className="mt-6 inline-block text-sm font-semibold text-teal-700 hover:underline">Return to dashboard</Link></section>;
}

export function NotFound() {
  return <main className="grid min-h-screen place-items-center bg-slate-50 px-6 dark:bg-slate-950"><section className="text-center"><p className="text-sm font-semibold text-teal-700">404</p><h1 className="mt-2 text-3xl font-semibold">Page not found</h1><p className="mt-2 text-slate-600 dark:text-slate-400">The page you requested does not exist.</p><Link to="/" className="mt-6 inline-block rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white">Return home</Link></section></main>;
}
