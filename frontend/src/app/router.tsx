import { createBrowserRouter } from "react-router-dom";
import { AccessDenied, NotFound } from "../components/common/States";
import { AppShell } from "../components/layout/AppShell";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { RoleGuard } from "../features/auth/RoleGuard";
import type { RoleName } from "../features/auth/types";
import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";

const guarded = (roles: readonly RoleName[], title: string) => <RoleGuard roles={roles}><PlaceholderPage title={title} /></RoleGuard>;

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { element: <ProtectedRoute />, children: [{ element: <AppShell />, children: [
    { index: true, element: <DashboardPage /> },
    { path: "my-complaints", element: guarded(["customer"], "My Complaints") },
    { path: "review-queue", element: guarded(["reviewer"], "Review Queue") },
    { path: "complaints", element: guarded(["reviewer"], "Complaints") },
    { path: "datasets", element: guarded(["administrator"], "Datasets") },
    { path: "benchmarks", element: guarded(["administrator"], "Benchmarks") },
    { path: "comparisons", element: guarded(["administrator"], "Comparisons") },
    { path: "model-promotions", element: guarded(["administrator"], "Model Promotions") },
    { path: "deployment-candidates", element: guarded(["administrator"], "Deployment Candidates") },
    { path: "deployment-history", element: guarded(["administrator"], "Deployment History") },
    { path: "access-denied", element: <AccessDenied /> },
  ] }] },
  { path: "*", element: <NotFound /> },
]);
