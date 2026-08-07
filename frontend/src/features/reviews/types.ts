import type { z } from "zod";
import type { reviewQueueItemSchema, reviewQueueResponseSchema, reviewQueueStatusSchema } from "./schemas";

export type ReviewQueueStatus = z.infer<typeof reviewQueueStatusSchema>;
export type ReviewQueueItem = z.infer<typeof reviewQueueItemSchema>;
export type ReviewQueueResponse = z.infer<typeof reviewQueueResponseSchema>;
export interface ReviewQueueParameters { offset: number; limit: number }
