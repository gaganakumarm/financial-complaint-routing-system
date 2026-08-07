import type { RoleName } from "../../features/auth/types";

export interface NavigationItem { label: string; path: string }

const navigation: Record<RoleName, NavigationItem[]> = {
  customer: [
    { label: "Dashboard", path: "/" },
    { label: "My Complaints", path: "/complaints" },
  ],
  reviewer: [
    { label: "Dashboard", path: "/" },
    { label: "Review Queue", path: "/review-queue" },
    { label: "Complaints", path: "/complaints" },
  ],
  administrator: [
    { label: "Dashboard", path: "/" },
    { label: "Datasets", path: "/datasets" },
    { label: "Benchmarks", path: "/benchmarks" },
    { label: "Comparisons", path: "/comparisons" },
    { label: "Model Promotions", path: "/model-promotions" },
    { label: "Deployment Candidates", path: "/deployment-candidates" },
    { label: "Deployment History", path: "/deployment-history" },
  ],
};

export const getNavigation = (role: RoleName): NavigationItem[] => navigation[role];
