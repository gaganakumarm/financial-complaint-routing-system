import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./useAuth";
import { authStorage } from "../../lib/authStorage";

const mocks = vi.hoisted(() => ({ getCurrentUser: vi.fn(), loginUser: vi.fn() }));
vi.mock("./authApi", () => mocks);
vi.mock("../../lib/api", () => ({ setUnauthorizedHandler: vi.fn() }));

function Consumer() { const { user, isRestoring, logout } = useAuth(); return <><p>{isRestoring ? "restoring" : user?.full_name ?? "anonymous"}</p><button onClick={logout}>Log out</button></>; }

describe("AuthProvider", () => {
  it("restores a stored session", async () => { authStorage.setToken("token"); mocks.getCurrentUser.mockResolvedValue({ full_name: "Restored User", role_name: "reviewer" }); render(<AuthProvider><Consumer /></AuthProvider>); expect(screen.getByText("restoring")).toBeInTheDocument(); await waitFor(() => expect(screen.getByText("Restored User")).toBeInTheDocument()); });
  it("clears authentication on logout", async () => { authStorage.setToken("token"); mocks.getCurrentUser.mockResolvedValue({ full_name: "User", role_name: "customer" }); render(<AuthProvider><Consumer /></AuthProvider>); await screen.findByText("User"); await userEvent.click(screen.getByRole("button", { name: "Log out" })); expect(screen.getByText("anonymous")).toBeInTheDocument(); expect(authStorage.getToken()).toBeNull(); });
});
