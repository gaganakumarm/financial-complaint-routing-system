import type { ReactNode } from "react";
import { AccessDenied } from "../../components/common/States";
import type { RoleName } from "./types";
import { useAuth } from "./useAuth";

export function RoleGuard({ roles, children }: { roles: readonly RoleName[]; children: ReactNode }) {
  const { hasAnyRole } = useAuth();
  return hasAnyRole(roles) ? children : <AccessDenied />;
}
