import type { ReferenceItem, ReviewerComplaint, ReviewerPrediction, ReviewQueueItem } from "./types";

export const reviewQueueItem: ReviewQueueItem = {
  complaint_id: "cc5e489f-d442-4594-ab1f-0d4cc81571b2",
  reference_number: "FCR-QUEUE-001",
  title: "Duplicate card transaction",
  current_status: "awaiting_review",
  created_at: "2026-08-08T08:00:00Z",
  updated_at: "2026-08-08T09:30:00Z",
};

export const categoryReference: ReferenceItem = { id: "8fe76b1a-51cc-4763-8d46-3da53d23395d", name: "Card transaction dispute", description: "Card transaction issues", active: true };
export const departmentReference: ReferenceItem = { id: "cbec32dc-6335-44bd-866e-3f6c74e86838", name: "Card Operations", description: "Card support team", active: true };

export const reviewerComplaint: ReviewerComplaint = {
  id: reviewQueueItem.complaint_id,
  reference_number: reviewQueueItem.reference_number,
  title: reviewQueueItem.title,
  description: "The same transaction appeared twice on the statement.",
  status: "under_review",
  final_category_id: categoryReference.id,
  final_department_id: departmentReference.id,
  final_urgency: "high",
  created_at: reviewQueueItem.created_at,
  updated_at: reviewQueueItem.updated_at,
};

export const reviewerPrediction: ReviewerPrediction = {
  id: "65c32b5c-d8e6-4db4-bfac-fd4e86af5b83",
  complaint_id: reviewerComplaint.id,
  model_version_id: "d69ad209-bf23-4085-8982-7aab7d8a55c7",
  predicted_category_id: categoryReference.id,
  predicted_department_id: departmentReference.id,
  predicted_urgency: "high",
  confidence_score: 0.92,
  output_valid: true,
  failure_code: null,
  inference_latency_ms: 18,
  created_at: "2026-08-08T08:30:00Z",
  category: { id: categoryReference.id, name: categoryReference.name },
  department: { id: departmentReference.id, name: departmentReference.name },
  model_version: { id: "d69ad209-bf23-4085-8982-7aab7d8a55c7", name: "Complaint Router", version: "v2" },
};
