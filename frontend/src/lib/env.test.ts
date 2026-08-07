import { describe, expect, it } from "vitest";
import { parseApiBaseUrl } from "./env";

describe("parseApiBaseUrl", () => {
  it("trims whitespace and trailing slashes", () => expect(parseApiBaseUrl("  http://localhost:8000/api/// ")).toBe("http://localhost:8000/api"));
  it("rejects missing and invalid values", () => {
    expect(() => parseApiBaseUrl(undefined)).toThrow("VITE_API_BASE_URL is required");
    expect(() => parseApiBaseUrl("relative/api")).toThrow("valid absolute URL");
  });
});
