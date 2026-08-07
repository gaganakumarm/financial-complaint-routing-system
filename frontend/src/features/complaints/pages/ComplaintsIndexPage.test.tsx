import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderComplaintUi } from "../testUtils";
import { ComplaintsIndexPage } from "./ComplaintsIndexPage";

const mocks = vi.hoisted(() => ({ role: "customer", useComplaints: vi.fn() }));
vi.mock("../../auth/useAuth", () => ({ useAuth: () => ({ user: { role_name: mocks.role } }) }));
vi.mock("../hooks", () => ({ useComplaints: mocks.useComplaints }));

describe("ComplaintsIndexPage", () => {
  it("allows customers into their complaint module", () => { mocks.role = "customer"; mocks.useComplaints.mockReturnValue({ isPending: false, isError: false, data: { items: [], count: 0 } }); renderComplaintUi(<ComplaintsIndexPage />); expect(screen.getByText("My Complaints")).toBeInTheDocument(); });
  it("keeps the reviewer complaint placeholder separate", () => { mocks.role = "reviewer"; renderComplaintUi(<ComplaintsIndexPage />); expect(screen.getByText("Complaints is coming next")).toBeInTheDocument(); });
  it("denies unsupported roles", () => { mocks.role = "administrator"; renderComplaintUi(<ComplaintsIndexPage />); expect(screen.getByText("Access denied")).toBeInTheDocument(); });
});
