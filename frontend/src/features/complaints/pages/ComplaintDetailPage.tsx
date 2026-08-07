import { Link, useParams } from "react-router-dom";
import { AccessDenied, ErrorState, LoadingState } from "../../../components/common/States";
import { getApiStatus } from "../../../lib/api";
import { ComplaintDetails } from "../components/ComplaintDetails";
import { useComplaint } from "../hooks";

export function ComplaintDetailPage() {
  const { complaintId = "" } = useParams();
  const query = useComplaint(complaintId);
  const status = getApiStatus(query.error);
  return <section><Link to="/complaints" className="text-sm font-semibold text-teal-700 hover:underline dark:text-teal-400">← Back to complaints</Link><div className="mt-5">{query.isPending ? <LoadingState label="Loading complaint" /> : status === 403 ? <AccessDenied /> : query.isError ? <ErrorState title={status === 404 ? "Complaint not found" : "Unable to load complaint"} message={status === 404 ? "This complaint does not exist or is not available to your account." : "The complaint could not be loaded."} onRetry={status === 404 ? undefined : () => void query.refetch()} /> : <ComplaintDetails complaint={query.data} />}</div></section>;
}
