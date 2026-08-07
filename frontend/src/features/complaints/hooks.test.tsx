import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { complaint } from "./fixtures.test-helper";
import { complaintKeys } from "./queryKeys";
import { useCreateComplaint } from "./hooks";

const mocks = vi.hoisted(() => ({ createComplaint: vi.fn() }));
vi.mock("./api", () => ({
  createComplaint: mocks.createComplaint,
  getComplaint: vi.fn(),
  listComplaints: vi.fn(),
}));

describe("useCreateComplaint", () => {
  it("creates, caches the detail, and invalidates complaint lists", async () => {
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    mocks.createComplaint.mockResolvedValue(complaint);
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useCreateComplaint(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ title: complaint.title, description: complaint.description });
    });

    expect(mocks.createComplaint).toHaveBeenCalledWith({ title: complaint.title, description: complaint.description });
    expect(client.getQueryData(complaintKeys.detail(complaint.id))).toEqual(complaint);
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: complaintKeys.lists() }));
  });
});
