import { describe, expect, it } from "vitest";
import { authStorage } from "./authStorage";

describe("authStorage", () => {
  it("stores, reads, and clears one access token", () => { authStorage.setToken(" token "); expect(authStorage.getToken()).toBe("token"); authStorage.clearToken(); expect(authStorage.getToken()).toBeNull(); });
  it("rejects blank tokens", () => expect(() => authStorage.setToken("  ")).toThrow());
});
