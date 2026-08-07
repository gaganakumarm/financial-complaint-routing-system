import { useQuery } from "@tanstack/react-query";
import { listReviewQueue } from "./api";
import { reviewKeys } from "./queryKeys";
import type { ReviewQueueParameters } from "./types";

export function useReviewQueue(parameters: ReviewQueueParameters) {
  return useQuery({
    queryKey: reviewKeys.queue(parameters),
    queryFn: () => listReviewQueue(parameters),
  });
}
