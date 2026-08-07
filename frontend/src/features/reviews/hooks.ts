import { useQuery } from "@tanstack/react-query";
import { getReviewerComplaint, listComplaintCategories, listComplaintPredictions, listDepartments, listReviewQueue } from "./api";
import { reviewKeys } from "./queryKeys";
import type { ReviewQueueParameters } from "./types";

export function useReviewQueue(parameters: ReviewQueueParameters) {
  return useQuery({
    queryKey: reviewKeys.queue(parameters),
    queryFn: () => listReviewQueue(parameters),
  });
}

export function useReviewerComplaint(complaintId: string) {
  return useQuery({ queryKey: reviewKeys.detail(complaintId), queryFn: () => getReviewerComplaint(complaintId), enabled: Boolean(complaintId), retry: 1 });
}

export function useComplaintPredictions(complaintId: string) {
  return useQuery({ queryKey: reviewKeys.predictions(complaintId), queryFn: () => listComplaintPredictions(complaintId), enabled: Boolean(complaintId), retry: 1 });
}

export function useComplaintCategories() {
  return useQuery({ queryKey: reviewKeys.categories(), queryFn: listComplaintCategories, staleTime: 5 * 60_000 });
}

export function useDepartments() {
  return useQuery({ queryKey: reviewKeys.departments(), queryFn: listDepartments, staleTime: 5 * 60_000 });
}
