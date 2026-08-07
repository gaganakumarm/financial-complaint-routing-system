import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { complaintStatuses } from "../types";
import { ComplaintStatusBadge } from "./ComplaintStatusBadge";

describe("ComplaintStatusBadge", () => {
  it.each(complaintStatuses)("renders readable text for %s", (status) => { render(<ComplaintStatusBadge status={status} />); expect(screen.getByText(status.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" "), { exact: false })).toBeInTheDocument(); });
});
