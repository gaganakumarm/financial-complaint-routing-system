import { api } from "../../lib/api";
import { predictionListResponseSchema, referenceListResponseSchema, reviewerComplaintSchema, reviewQueueResponseSchema } from "./schemas";
import type { PredictionListResponse, ReferenceListResponse, ReviewerComplaint, ReviewQueueParameters, ReviewQueueResponse } from "./types";

export async function listReviewQueue(parameters: ReviewQueueParameters): Promise<ReviewQueueResponse> {
  const { data } = await api.get<unknown>("/reviews/queue", { params: parameters });
  return reviewQueueResponseSchema.parse(data);
}

export async function getReviewerComplaint(complaintId: string): Promise<ReviewerComplaint> {
  const { data } = await api.get<unknown>(`/reviews/complaints/${complaintId}`);
  return reviewerComplaintSchema.parse(data);
}

export async function listComplaintPredictions(complaintId: string): Promise<PredictionListResponse> {
  const { data } = await api.get<unknown>(`/predictions/complaints/${complaintId}`, { params: { offset: 0, limit: 100 } });
  return predictionListResponseSchema.parse(data);
}

export async function listComplaintCategories(): Promise<ReferenceListResponse> {
  const { data } = await api.get<unknown>("/reference/complaint-categories");
  return referenceListResponseSchema.parse(data);
}

export async function listDepartments(): Promise<ReferenceListResponse> {
  const { data } = await api.get<unknown>("/reference/departments");
  return referenceListResponseSchema.parse(data);
}
