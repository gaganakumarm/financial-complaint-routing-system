import type { ComplaintListParameters } from "./types";

export const complaintKeys = {
  all: ["complaints"] as const,
  lists: () => [...complaintKeys.all, "list"] as const,
  list: (parameters: ComplaintListParameters) => [...complaintKeys.lists(), parameters] as const,
  details: () => [...complaintKeys.all, "detail"] as const,
  detail: (complaintId: string) => [...complaintKeys.details(), complaintId] as const,
};
