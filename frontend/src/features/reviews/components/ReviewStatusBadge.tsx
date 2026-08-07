import type { ReviewQueueStatus } from "../types";

const statuses: Record<ReviewQueueStatus, { label: string; className: string }> = {
  submitted: { label: "Submitted", className: "bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200" },
  prediction_pending: { label: "Prediction pending", className: "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200" },
  prediction_completed: { label: "Prediction completed", className: "bg-cyan-50 text-cyan-800 dark:bg-cyan-950 dark:text-cyan-200" },
  awaiting_review: { label: "Awaiting review", className: "bg-violet-50 text-violet-800 dark:bg-violet-950 dark:text-violet-200" },
  under_review: { label: "Under review", className: "bg-purple-50 text-purple-800 dark:bg-purple-950 dark:text-purple-200" },
  routed: { label: "Routed", className: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" },
  closed: { label: "Closed", className: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100" },
  prediction_failed: { label: "Prediction failed", className: "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200" },
};

export function ReviewStatusBadge({ status }: { status: ReviewQueueStatus }) {
  const presentation = statuses[status];
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${presentation.className}`}>{presentation.label}</span>;
}
