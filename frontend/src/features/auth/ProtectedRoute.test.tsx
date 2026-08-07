import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "./ProtectedRoute";

const auth = vi.hoisted(() => ({ value: { user: null as object | null, isRestoring: false } }));
vi.mock("./useAuth", () => ({ useAuth: () => auth.value }));

function subject() { return render(<MemoryRouter initialEntries={["/private"]}><Routes><Route path="/login" element={<p>Login page</p>} /><Route element={<ProtectedRoute />}><Route path="/private" element={<p>Private page</p>} /></Route></Routes></MemoryRouter>); }

describe("ProtectedRoute", () => {
  it("redirects an anonymous user", () => { auth.value = { user: null, isRestoring: false }; subject(); expect(screen.getByText("Login page")).toBeInTheDocument(); });
  it("renders an authenticated route", () => { auth.value = { user: {}, isRestoring: false }; subject(); expect(screen.getByText("Private page")).toBeInTheDocument(); });
});
