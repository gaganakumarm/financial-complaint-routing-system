import { z } from "zod";

export const reviewQueueStatusSchema = z.enum([
  "submitted",
  "prediction_pending",
  "prediction_completed",
  "awaiting_review",
  "under_review",
  "routed",
  "closed",
  "prediction_failed",
]);

export const reviewQueueItemSchema = z.object({
  complaint_id: z.uuid(),
  reference_number: z.string().min(1),
  title: z.string().min(1),
  current_status: reviewQueueStatusSchema,
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

export const reviewQueueResponseSchema = z.object({
  items: z.array(reviewQueueItemSchema),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().min(1).max(500),
  count: z.number().int().nonnegative(),
});

export const reviewerComplaintSchema = z.object({
  id: z.uuid(),
  reference_number: z.string().min(1),
  title: z.string().min(1),
  description: z.string(),
  status: reviewQueueStatusSchema,
  final_category_id: z.uuid().nullable(),
  final_department_id: z.uuid().nullable(),
  final_urgency: z.enum(["low", "medium", "high", "critical"]).nullable(),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

const semanticSummarySchema = z.object({ id: z.uuid(), name: z.string().min(1) });

export const reviewerPredictionSchema = z.object({
  id: z.uuid(),
  complaint_id: z.uuid(),
  model_version_id: z.uuid(),
  predicted_category_id: z.uuid().nullable(),
  predicted_department_id: z.uuid().nullable(),
  predicted_urgency: z.enum(["low", "medium", "high", "critical"]).nullable(),
  confidence_score: z.union([z.number(), z.string()]).transform((value) => Number(value)).pipe(z.number().min(0).max(1)).nullable(),
  output_valid: z.boolean(),
  failure_code: z.string().nullable(),
  inference_latency_ms: z.number().int().nonnegative().nullable(),
  created_at: z.iso.datetime({ offset: true }),
  category: semanticSummarySchema.nullable(),
  department: semanticSummarySchema.nullable(),
  model_version: semanticSummarySchema.extend({ version: z.string().min(1) }),
});

export const predictionListResponseSchema = z.object({
  items: z.array(reviewerPredictionSchema),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().min(1).max(500),
  count: z.number().int().nonnegative(),
});

export const referenceItemSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
  description: z.string().nullable(),
  active: z.boolean(),
});

export const referenceListResponseSchema = z.object({
  items: z.array(referenceItemSchema),
  count: z.number().int().nonnegative(),
});
