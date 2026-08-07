import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createComplaint, getComplaint, listComplaints } from "./api";
import { complaintKeys } from "./queryKeys";
import type { ComplaintCreateInput, ComplaintListParameters } from "./types";

export function useComplaints(parameters: ComplaintListParameters) {
  return useQuery({ queryKey: complaintKeys.list(parameters), queryFn: () => listComplaints(parameters) });
}

export function useComplaint(complaintId: string) {
  return useQuery({ queryKey: complaintKeys.detail(complaintId), queryFn: () => getComplaint(complaintId), enabled: Boolean(complaintId), retry: (count, error) => count < 1 && (error as { response?: { status?: number } }).response?.status !== 404 });
}

export function useCreateComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ComplaintCreateInput) => createComplaint(input),
    onSuccess: (complaint) => {
      queryClient.setQueryData(complaintKeys.detail(complaint.id), complaint);
      void queryClient.invalidateQueries({ queryKey: complaintKeys.lists() });
    },
  });
}
