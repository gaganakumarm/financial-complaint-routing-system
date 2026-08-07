import { screen } from "@testing-library/react";
import { AxiosError, type AxiosResponse } from "axios";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RoleGuard } from "../../auth/RoleGuard";
import type { RoleName } from "../../auth/types";
import { categoryReference, departmentReference, reviewerComplaint, reviewerPrediction } from "../fixtures.test-helper";
import { renderReviewUi } from "../testUtils";
import { ReviewDetailPage } from "./ReviewDetailPage";

const mocks = vi.hoisted(() => ({
  role: "reviewer" as RoleName,
  complaint: vi.fn(),
  predictions: vi.fn(),
  categories: vi.fn(),
  departments: vi.fn(),
}));

vi.mock("../hooks", () => ({
  useReviewerComplaint: mocks.complaint,
  useComplaintPredictions: mocks.predictions,
  useComplaintCategories: mocks.categories,
  useDepartments: mocks.departments,
}));
vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ hasAnyRole: (roles: readonly RoleName[]) => roles.includes(mocks.role) }),
}));

const success = <T,>(data: T) => ({ isPending: false, isError: false, data, refetch: vi.fn() });
const apiError = (status: number) => new AxiosError("request failed", "ERR", undefined, undefined, { status } as AxiosResponse);

function arrange() {
  mocks.complaint.mockReturnValue(success(reviewerComplaint));
  mocks.predictions.mockReturnValue(success({ items: [reviewerPrediction], count: 1, offset: 0, limit: 100 }));
  mocks.categories.mockReturnValue(success({ items: [categoryReference], count: 1 }));
  mocks.departments.mockReturnValue(success({ items: [departmentReference], count: 1 }));
}

function renderPage(guarded = false) {
  const element = guarded ? <RoleGuard roles={["reviewer", "administrator"]}><ReviewDetailPage /></RoleGuard> : <ReviewDetailPage />;
  return renderReviewUi(<Routes><Route path="/review-queue/:complaintId" element={element} /></Routes>, [`/review-queue/${reviewerComplaint.id}`]);
}

describe("ReviewDetailPage", () => {
  it("shows required complaint loading", () => { arrange(); mocks.complaint.mockReturnValue({ isPending: true }); renderPage(); expect(screen.getByText(/Loading complaint workspace/)).toBeInTheDocument(); });

  it("renders complaint details from a deep link", () => { arrange(); renderPage(); expect(screen.getByText(reviewerComplaint.description)).toBeInTheDocument(); expect(screen.getByText(reviewerComplaint.reference_number)).toBeInTheDocument(); expect(screen.getByText("Under review")).toBeInTheDocument(); expect(mocks.complaint).toHaveBeenCalledWith(reviewerComplaint.id); expect(mocks.predictions).toHaveBeenCalledWith(reviewerComplaint.id); });

  it("renders complaint not found", () => { arrange(); mocks.complaint.mockReturnValue({ isPending: false, isError: true, error: apiError(404) }); renderPage(); expect(screen.getByRole("alert")).toHaveTextContent("Complaint not found"); });

  it("renders complaint access denied", () => { arrange(); mocks.complaint.mockReturnValue({ isPending: false, isError: true, error: apiError(403) }); renderPage(); expect(screen.getByText("Access denied")).toBeInTheDocument(); });

  it("shows semantic prediction evidence", () => { arrange(); renderPage(); expect(screen.getAllByText(categoryReference.name)).not.toHaveLength(0); expect(screen.getAllByText(departmentReference.name)).not.toHaveLength(0); expect(screen.getByText("Complaint Router · v2")).toBeInTheDocument(); expect(screen.getByText("92%")).toBeInTheDocument(); expect(screen.getByText("Valid output")).toBeInTheDocument(); });

  it("shows a nonfatal empty prediction state", () => { arrange(); mocks.predictions.mockReturnValue(success({ items: [], count: 0, offset: 0, limit: 100 })); renderPage(); expect(screen.getByText("No prediction is available for this complaint yet.")).toBeInTheDocument(); expect(screen.getByText(reviewerComplaint.description)).toBeInTheDocument(); });

  it("isolates prediction fetch failure", () => { arrange(); mocks.predictions.mockReturnValue({ isPending: false, isError: true, refetch: vi.fn() }); renderPage(); expect(screen.getByRole("alert", { name: "" })).toHaveTextContent("Unable to load prediction"); expect(screen.getByText(reviewerComplaint.description)).toBeInTheDocument(); });

  it("resolves final routing IDs to semantic names", () => { arrange(); renderPage(); const summary = screen.getByRole("heading", { name: "Final routing summary" }).parentElement!; expect(summary).toHaveTextContent(categoryReference.name); expect(summary).toHaveTextContent(departmentReference.name); expect(summary).toHaveTextContent("High"); });

  it("shows not finalized when final routing is absent", () => { arrange(); mocks.complaint.mockReturnValue(success({ ...reviewerComplaint, final_category_id: null, final_department_id: null, final_urgency: null })); renderPage(); expect(screen.getAllByText("Not finalized")).toHaveLength(3); });

  it("isolates reference-data failure", () => { arrange(); mocks.categories.mockReturnValue({ isPending: false, isError: true, refetch: vi.fn() }); renderPage(); expect(screen.getByRole("alert")).toHaveTextContent("Categories unavailable"); expect(screen.getAllByText(departmentReference.name)).not.toHaveLength(0); expect(screen.getByText(reviewerComplaint.description)).toBeInTheDocument(); });

  it.each(["reviewer", "administrator"] as const)("allows %s access", (role) => { arrange(); mocks.role = role; renderPage(true); expect(screen.getByText("Review workspace")).toBeInTheDocument(); });

  it("denies customer access", () => { arrange(); mocks.role = "customer"; renderPage(true); expect(screen.getByText("Access denied")).toBeInTheDocument(); });
});
