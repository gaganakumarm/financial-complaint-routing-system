import type { ReviewQueueParameters } from "./types";

export const reviewKeys = {
  all: ["reviews"] as const,
  queues: () => [...reviewKeys.all, "queue"] as const,
  queue: (parameters: ReviewQueueParameters) => [...reviewKeys.queues(), parameters] as const,
};
