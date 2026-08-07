import { Link, useParams } from "react-router-dom";
import { AccessDenied, ErrorState, LoadingState } from "../../../components/common/States";
import { getApiStatus } from "../../../lib/api";
import { PredictionPanel } from "../components/PredictionPanel";
import { ReferenceDataSummary } from "../components/ReferenceDataSummary";
import { ReviewerComplaintDetails } from "../components/ReviewerComplaintDetails";
import { ReviewStatusBadge } from "../components/ReviewStatusBadge";
import { useComplaintCategories, useComplaintPredictions, useDepartments, useReviewerComplaint } from "../hooks";

export function ReviewDetailPage() {
  const { complaintId = "" } = useParams();
  const complaintQuery = useReviewerComplaint(complaintId);
  const predictionQuery = useComplaintPredictions(complaintId);
  const categoriesQuery = useComplaintCategories();
  const departmentsQuery = useDepartments();
  const complaintStatus = getApiStatus(complaintQuery.error);

  if (complaintQuery.isPending) return <LoadingState label="Loading complaint workspace" />;
  if (complaintStatus === 403) return <AccessDenied />;
  if (complaintQuery.isError) return <ErrorState title={complaintStatus === 404 ? "Complaint not found" : "Unable to load complaint"} message={complaintStatus === 404 ? "This complaint does not exist or is no longer available for review." : "The reviewer workspace could not be loaded."} onRetry={complaintStatus === 404 ? undefined : () => void complaintQuery.refetch()} />;

  const complaint = complaintQuery.data;
  return <section><Link to="/review-queue" className="text-sm font-semibold text-teal-700 hover:underline dark:text-teal-400">← Back to Review Queue</Link><header className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-medium text-slate-500">{complaint.reference_number}</p><h1 className="mt-1 text-2xl font-semibold">Review workspace</h1></div><ReviewStatusBadge status={complaint.status} /></header><div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)]"><ReviewerComplaintDetails complaint={complaint} /><PredictionPanel data={predictionQuery.data} isPending={predictionQuery.isPending} isError={predictionQuery.isError} onRetry={() => void predictionQuery.refetch()} /></div><div className="mt-6"><ReferenceDataSummary complaint={complaint} categories={categoriesQuery.data} departments={departmentsQuery.data} categoriesPending={categoriesQuery.isPending} departmentsPending={departmentsQuery.isPending} categoriesError={categoriesQuery.isError} departmentsError={departmentsQuery.isError} retryCategories={() => void categoriesQuery.refetch()} retryDepartments={() => void departmentsQuery.refetch()} /></div></section>;
}
