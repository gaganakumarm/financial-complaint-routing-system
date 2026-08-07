import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RoleGuard } from "../../auth/RoleGuard";
import type { RoleName } from "../../auth/types";
import { reviewQueueItem } from "../fixtures.test-helper";
import { renderReviewUi } from "../testUtils";
import { ReviewQueuePage } from "./ReviewQueuePage";

const mocks = vi.hoisted(() => ({
  role: "reviewer" as RoleName,
  useReviewQueue: vi.fn(),
}));

vi.mock("../hooks", () => ({ useReviewQueue: mocks.useReviewQueue }));
vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    hasAnyRole: (roles: readonly RoleName[]) => roles.includes(mocks.role),
  }),
}));

const queueData = (items = [reviewQueueItem], count = items.length) => ({
  isPending: false,
  isError: false,
  isFetching: false,
  data: { items, count, offset: 0, limit: 100 },
});

describe("ReviewQueuePage", () => {
  it("shows the loading state", () => {
    mocks.useReviewQueue.mockReturnValue({ isPending: true });
    renderReviewUi(<ReviewQueuePage />);
    expect(screen.getByText(/Loading review queue/)).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    mocks.useReviewQueue.mockReturnValue(queueData([]));
    renderReviewUi(<ReviewQueuePage />);
    expect(screen.getByText("The review queue is empty")).toBeInTheDocument();
  });

  it("renders the backend queue fields and open-review link", () => {
    mocks.useReviewQueue.mockReturnValue(queueData());
    renderReviewUi(<ReviewQueuePage />);
    expect(screen.getByText(reviewQueueItem.reference_number)).toBeInTheDocument();
    expect(screen.getByText(reviewQueueItem.title)).toBeInTheDocument();
    expect(screen.getByText("Awaiting review")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Review/ })).toHaveAttribute(
      "href",
      `/review-queue/${reviewQueueItem.complaint_id}`,
    );
    expect(screen.getByRole("columnheader", { name: "Created" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Updated" })).toBeInTheDocument();
  });

  it("shows a retryable error", async () => {
    const refetch = vi.fn();
    mocks.useReviewQueue.mockReturnValue({ isPending: false, isError: true, refetch });
    renderReviewUi(<ReviewQueuePage />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load review queue");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("moves through offset pagination in 100-item pages", async () => {
    const items = Array.from({ length: 100 }, (_, index) => ({
      ...reviewQueueItem,
      complaint_id: `00000000-0000-4000-8000-${index.toString().padStart(12, "0")}`,
      reference_number: `FCR-${index + 1}`,
    }));
    mocks.useReviewQueue.mockReturnValue(queueData(items, 100));
    renderReviewUi(<ReviewQueuePage />);
    expect(mocks.useReviewQueue).toHaveBeenLastCalledWith({ offset: 0, limit: 100 });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(mocks.useReviewQueue).toHaveBeenLastCalledWith({ offset: 100, limit: 100 });
  });

  it.each(["reviewer", "administrator"] as const)("allows the %s role", (role) => {
    mocks.role = role;
    mocks.useReviewQueue.mockReturnValue(queueData([]));
    renderReviewUi(<RoleGuard roles={["reviewer", "administrator"]}><ReviewQueuePage /></RoleGuard>);
    expect(screen.getByText("The review queue is empty")).toBeInTheDocument();
  });

  it("denies customers", () => {
    mocks.role = "customer";
    mocks.useReviewQueue.mockReturnValue(queueData([]));
    renderReviewUi(<RoleGuard roles={["reviewer", "administrator"]}><ReviewQueuePage /></RoleGuard>);
    expect(screen.getByText("Access denied")).toBeInTheDocument();
  });
});
