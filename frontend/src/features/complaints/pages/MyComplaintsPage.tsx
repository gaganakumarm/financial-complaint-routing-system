import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../../../components/common/States";
import { ComplaintTable } from "../components/ComplaintTable";
import { useComplaints } from "../hooks";

const PAGE_SIZE = 20;

export function MyComplaintsPage() {
  const [offset, setOffset] = useState(0);
  const query = useComplaints({ offset, limit: PAGE_SIZE });
  return <section><div className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-semibold">My Complaints</h2><p className="mt-1 text-sm text-slate-600 dark:text-slate-400">Track complaints submitted through your account.</p></div><Link to="/complaints/new" className="rounded-md bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-800">Create complaint</Link></div>
    {query.isPending ? <LoadingState label="Loading complaints" /> : query.isError ? <ErrorState title="Unable to load complaints" message="Your complaints could not be loaded." onRetry={() => void query.refetch()} /> : query.data.items.length === 0 && offset === 0 ? <EmptyState title="No complaints submitted" message="Create your first complaint when you are ready." /> : <><ComplaintTable complaints={query.data.items} /><nav aria-label="Complaint pagination" className="mt-4 flex items-center justify-between"><button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><p className="text-sm text-slate-500">Showing {offset + 1}–{offset + query.data.count}</p><button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" disabled={query.data.count < PAGE_SIZE || query.isFetching} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></nav></>}
  </section>;
}
