import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { setUnauthorizedHandler } from "../../lib/api";
import { authStorage } from "../../lib/authStorage";
import { queryClient } from "../../lib/queryClient";
import { getCurrentUser, loginUser } from "./authApi";
import { AuthContext } from "./AuthContext";
import { hasAnyRole } from "./roles";
import type { LoginCredentials, RoleName, User } from "./types";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  const logout = useCallback(() => {
    authStorage.clearToken();
    setUser(null);
    queryClient.clear();
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(undefined);
  }, [logout]);

  useEffect(() => {
    let active = true;
    async function restore() {
      if (!authStorage.getToken()) { if (active) setIsRestoring(false); return; }
      try {
        const restored = await getCurrentUser();
        if (active) setUser(restored);
      } catch {
        authStorage.clearToken();
      } finally {
        if (active) setIsRestoring(false);
      }
    }
    void restore();
    return () => { active = false; };
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const tokens = await loginUser(credentials);
    authStorage.setToken(tokens.access_token);
    try {
      setUser(await getCurrentUser());
    } catch (error) {
      authStorage.clearToken();
      throw error;
    }
  }, []);

  const value = useMemo(() => ({
    user,
    isRestoring,
    login,
    logout,
    hasRole: (role: RoleName) => user?.role_name === role,
    hasAnyRole: (allowed: readonly RoleName[]) => Boolean(user && hasAnyRole(user.role_name, allowed)),
  }), [isRestoring, login, logout, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
