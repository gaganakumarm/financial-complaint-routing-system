import { api } from "../../lib/api";
import { reviewQueueResponseSchema } from "./schemas";
import type { ReviewQueueParameters, ReviewQueueResponse } from "./types";

export async function listReviewQueue(parameters: ReviewQueueParameters): Promise<ReviewQueueResponse> {
  const { data } = await api.get<unknown>("/reviews/queue", { params: parameters });
  return reviewQueueResponseSchema.parse(data);
}
