import type { ReviewerComplaint } from "../types";

const formatDate = (value: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "long", timeStyle: "short" }).format(new Date(value));

export function ReviewerComplaintDetails({ complaint }: { complaint: ReviewerComplaint }) {
  return <section aria-labelledby="complaint-details-heading" className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"><h2 id="complaint-details-heading" className="text-lg font-semibold">Complaint details</h2><h3 className="mt-5 font-semibold">{complaint.title}</h3><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700 dark:text-slate-300">{complaint.description}</p><dl className="mt-6 grid gap-5 border-t border-slate-200 pt-5 text-sm dark:border-slate-800 sm:grid-cols-2"><div><dt className="text-slate-500">Created</dt><dd className="mt-1 font-medium">{formatDate(complaint.created_at)}</dd></div><div><dt className="text-slate-500">Last updated</dt><dd className="mt-1 font-medium">{formatDate(complaint.updated_at)}</dd></div></dl></section>;
}
