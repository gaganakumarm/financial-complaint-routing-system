export const complaintStatuses = [
  "submitted",
  "prediction_pending",
  "prediction_completed",
  "awaiting_review",
  "under_review",
  "routed",
  "closed",
  "prediction_failed",
] as const;

export type ComplaintStatus = (typeof complaintStatuses)[number];
export type ComplaintUrgency = "low" | "medium" | "high" | "critical";

export interface Complaint {
  id: string;
  reference_number: string;
  customer_id: string;
  title: string;
  description: string;
  current_status: ComplaintStatus;
  final_category_id: string | null;
  final_department_id: string | null;
  final_urgency: ComplaintUrgency | null;
  created_at: string;
  updated_at: string;
}

export interface ComplaintListResponse {
  items: Complaint[];
  offset: number;
  limit: number;
  count: number;
}

export interface ComplaintCreateInput { title: string; description: string }
export interface ComplaintCreateResponse { complaint: Complaint }
export interface ComplaintListParameters { offset: number; limit: number }
