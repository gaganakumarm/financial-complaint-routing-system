import { describe, expect, it } from "vitest";
import { loginSchema } from "./schema";

describe("loginSchema", () => {
  it("accepts valid credentials", () => expect(loginSchema.safeParse({ email: "user@example.com", password: "password" }).success).toBe(true));
  it("rejects invalid email and blank password", () => expect(loginSchema.safeParse({ email: "bad", password: "" }).success).toBe(false));
});
