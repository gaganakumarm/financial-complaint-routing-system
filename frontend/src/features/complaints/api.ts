import { api } from "../../lib/api";
import type { Complaint, ComplaintCreateInput, ComplaintCreateResponse, ComplaintListParameters, ComplaintListResponse } from "./types";

export async function listComplaints(parameters: ComplaintListParameters): Promise<ComplaintListResponse> {
  const { data } = await api.get<ComplaintListResponse>("/complaints", { params: parameters });
  return data;
}

export async function getComplaint(complaintId: string): Promise<Complaint> {
  const { data } = await api.get<Complaint>(`/complaints/${complaintId}`);
  return data;
}

export async function createComplaint(input: ComplaintCreateInput): Promise<Complaint> {
  const { data } = await api.post<ComplaintCreateResponse>("/complaints", input);
  return data.complaint;
}
