import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderComplaintUi } from "../testUtils";
import { ComplaintForm } from "./ComplaintForm";

describe("ComplaintForm", () => {
  it("validates required fields", async () => { renderComplaintUi(<ComplaintForm onSubmit={vi.fn()} isPending={false} />); await userEvent.click(screen.getByRole("button", { name: "Submit complaint" })); expect(await screen.findByText("Title is required.")).toBeInTheDocument(); expect(screen.getByText("Description is required.")).toBeInTheDocument(); });
  it("submits trimmed valid values", async () => { const submit = vi.fn().mockResolvedValue(undefined); renderComplaintUi(<ComplaintForm onSubmit={submit} isPending={false} />); await userEvent.type(screen.getByLabelText("Title"), " Duplicate charge "); await userEvent.type(screen.getByLabelText("Description"), " Charged twice "); await userEvent.click(screen.getByRole("button", { name: "Submit complaint" })); expect(submit).toHaveBeenCalledWith({ title: "Duplicate charge", description: "Charged twice" }, expect.anything()); });
  it("renders a safe server validation error", () => { renderComplaintUi(<ComplaintForm onSubmit={vi.fn()} isPending={false} serverError={new Error("internal")} />); expect(screen.getByRole("alert")).toHaveTextContent("Unable to create the complaint"); });
});
