import type { ReviewQueueParameters } from "./types";

export const reviewKeys = {
  all: ["reviews"] as const,
  queues: () => [...reviewKeys.all, "queue"] as const,
  queue: (parameters: ReviewQueueParameters) => [...reviewKeys.queues(), parameters] as const,
  details: () => [...reviewKeys.all, "detail"] as const,
  detail: (complaintId: string) => [...reviewKeys.details(), complaintId] as const,
  predictions: (complaintId: string) => [...reviewKeys.all, "predictions", complaintId] as const,
  reference: () => [...reviewKeys.all, "reference"] as const,
  categories: () => [...reviewKeys.reference(), "categories"] as const,
  departments: () => [...reviewKeys.reference(), "departments"] as const,
};
