import { describe, expect, it } from "vitest";
import { getNavigation } from "./navigation";

describe("role navigation", () => {
  it("shows only customer links", () => expect(getNavigation("customer").map((item) => item.label)).toEqual(["Dashboard", "My Complaints"]));
  it("shows reviewer workflow", () => expect(getNavigation("reviewer").map((item) => item.label)).toContain("Review Queue"));
  it("shows administrator governance", () => { const labels = getNavigation("administrator").map((item) => item.label); expect(labels).toContain("Datasets"); expect(labels).toContain("Deployment History"); expect(labels).not.toContain("My Complaints"); });
});
