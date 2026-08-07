import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { complaint } from "../fixtures.test-helper";
import { renderComplaintUi } from "../testUtils";
import { MyComplaintsPage } from "./MyComplaintsPage";

const mocks = vi.hoisted(() => ({ useComplaints: vi.fn() }));
vi.mock("../hooks", () => ({ useComplaints: mocks.useComplaints }));

describe("MyComplaintsPage", () => {
  it("shows loading", () => { mocks.useComplaints.mockReturnValue({ isPending: true }); renderComplaintUi(<MyComplaintsPage />); expect(screen.getByText(/Loading complaints/)).toBeInTheDocument(); });
  it("shows an empty state", () => { mocks.useComplaints.mockReturnValue({ isPending: false, isError: false, data: { items: [], count: 0 } }); renderComplaintUi(<MyComplaintsPage />); expect(screen.getByText("No complaints submitted")).toBeInTheDocument(); });
  it("renders returned complaints", () => { mocks.useComplaints.mockReturnValue({ isPending: false, isError: false, isFetching: false, data: { items: [complaint], count: 1 } }); renderComplaintUi(<MyComplaintsPage />); expect(screen.getByText(complaint.title)).toBeInTheDocument(); expect(screen.getByText("Awaiting review")).toBeInTheDocument(); });
  it("shows a retryable API error", () => { mocks.useComplaints.mockReturnValue({ isPending: false, isError: true, refetch: vi.fn() }); renderComplaintUi(<MyComplaintsPage />); expect(screen.getByRole("alert")).toHaveTextContent("Unable to load complaints"); expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument(); });
});
