import { createBrowserRouter } from "react-router-dom";
import { AccessDenied, NotFound } from "../components/common/States";
import { AppShell } from "../components/layout/AppShell";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { RoleGuard } from "../features/auth/RoleGuard";
import type { RoleName } from "../features/auth/types";
import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { ComplaintDetailPage } from "../features/complaints/pages/ComplaintDetailPage";
import { CreateComplaintPage } from "../features/complaints/pages/CreateComplaintPage";
import { ComplaintsIndexPage } from "../features/complaints/pages/ComplaintsIndexPage";
import { ReviewQueuePage } from "../features/reviews/pages/ReviewQueuePage";

const guarded = (roles: readonly RoleName[], title: string) => <RoleGuard roles={roles}><PlaceholderPage title={title} /></RoleGuard>;

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { element: <ProtectedRoute />, children: [{ element: <AppShell />, children: [
    { index: true, element: <DashboardPage /> },
    { path: "complaints/new", element: <RoleGuard roles={["customer"]}><CreateComplaintPage /></RoleGuard> },
    { path: "complaints/:complaintId", element: <RoleGuard roles={["customer"]}><ComplaintDetailPage /></RoleGuard> },
    { path: "complaints", element: <ComplaintsIndexPage /> },
    { path: "review-queue", element: <RoleGuard roles={["reviewer", "administrator"]}><ReviewQueuePage /></RoleGuard> },
    { path: "review-queue/:complaintId", element: guarded(["reviewer", "administrator"], "Review Detail") },
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
