import { useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../../components/common/States";
import { ReviewQueueTable } from "../components/ReviewQueueTable";
import { useReviewQueue } from "../hooks";

export const REVIEW_QUEUE_PAGE_SIZE = 100;

export function ReviewQueuePage() {
  const [offset, setOffset] = useState(0);
  const query = useReviewQueue({ offset, limit: REVIEW_QUEUE_PAGE_SIZE });
  if (query.isPending) return <LoadingState label="Loading review queue" />;
  if (query.isError) return <ErrorState title="Unable to load review queue" message="The review queue could not be loaded." onRetry={() => void query.refetch()} />;
  const { items, count } = query.data;
  return <section><div className="mb-6"><h2 className="text-xl font-semibold">Review Queue</h2><p className="mt-1 text-sm text-slate-600 dark:text-slate-400">Complaints waiting for human review, ordered by submission time.</p></div>{items.length === 0 ? <><EmptyState title={offset === 0 ? "The review queue is empty" : "No complaints on this page"} message={offset === 0 ? "New complaints will appear here when review is required." : "Return to the previous page to continue reviewing complaints."} />{offset > 0 && <button className="mt-4 rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold dark:border-slate-700" onClick={() => setOffset(Math.max(0, offset - REVIEW_QUEUE_PAGE_SIZE))}>Previous</button>}</> : <><ReviewQueueTable items={items} /><nav aria-label="Review queue pagination" className="mt-4 flex items-center justify-between"><button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - REVIEW_QUEUE_PAGE_SIZE))}>Previous</button><p className="text-sm text-slate-500">Showing {offset + 1}–{offset + count}</p><button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" disabled={count < REVIEW_QUEUE_PAGE_SIZE || query.isFetching} onClick={() => setOffset(offset + REVIEW_QUEUE_PAGE_SIZE)}>Next</button></nav></>}</section>;
}
