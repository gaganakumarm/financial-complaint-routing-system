import type { z } from "zod";
import type { predictionListResponseSchema, referenceItemSchema, referenceListResponseSchema, reviewerComplaintSchema, reviewerPredictionSchema, reviewQueueItemSchema, reviewQueueResponseSchema, reviewQueueStatusSchema } from "./schemas";

export type ReviewQueueStatus = z.infer<typeof reviewQueueStatusSchema>;
export type ReviewQueueItem = z.infer<typeof reviewQueueItemSchema>;
export type ReviewQueueResponse = z.infer<typeof reviewQueueResponseSchema>;
export interface ReviewQueueParameters { offset: number; limit: number }
export type ReviewerComplaint = z.infer<typeof reviewerComplaintSchema>;
export type ReviewerPrediction = z.infer<typeof reviewerPredictionSchema>;
export type PredictionListResponse = z.infer<typeof predictionListResponseSchema>;
export type ReferenceItem = z.infer<typeof referenceItemSchema>;
export type ReferenceListResponse = z.infer<typeof referenceListResponseSchema>;
