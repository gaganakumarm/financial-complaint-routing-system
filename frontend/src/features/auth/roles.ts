import type { RoleName } from "./types";

export const hasRole = (role: RoleName, allowed: RoleName): boolean => role === allowed;
export const hasAnyRole = (role: RoleName, allowed: readonly RoleName[]): boolean => allowed.includes(role);
export const canAccess = hasAnyRole;
export const formatRole = (role: RoleName): string => role.charAt(0).toUpperCase() + role.slice(1);
