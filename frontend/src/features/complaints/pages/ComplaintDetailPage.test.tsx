import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import { complaint } from "../fixtures.test-helper";
import { renderComplaintUi } from "../testUtils";
import { ComplaintDetailPage } from "./ComplaintDetailPage";

const mocks = vi.hoisted(() => ({ useComplaint: vi.fn() }));
vi.mock("../hooks", () => ({ useComplaint: mocks.useComplaint }));

function renderPage() { return renderComplaintUi(<Routes><Route path="/complaints/:complaintId" element={<ComplaintDetailPage />} /></Routes>, [`/complaints/${complaint.id}`]); }

describe("ComplaintDetailPage", () => {
  it("renders customer-safe complaint details", () => { mocks.useComplaint.mockReturnValue({ isPending: false, isError: false, data: complaint }); renderPage(); expect(screen.getByText(complaint.title)).toBeInTheDocument(); expect(screen.getByText(complaint.description)).toBeInTheDocument(); expect(screen.getByText("A final routing outcome is not available yet.")).toBeInTheDocument(); });
  it("renders a safe not-found state", () => { const response = { status: 404 } as AxiosResponse; mocks.useComplaint.mockReturnValue({ isPending: false, isError: true, error: new AxiosError("missing", "ERR", undefined, undefined, response) }); renderPage(); expect(screen.getByRole("alert")).toHaveTextContent("Complaint not found"); });
});
