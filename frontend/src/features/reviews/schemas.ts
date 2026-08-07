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
