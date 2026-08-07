import { createContext } from "react";
import type { LoginCredentials, RoleName, User } from "./types";

export interface AuthContextValue {
  user: User | null;
  isRestoring: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => void;
  hasRole: (role: RoleName) => boolean;
  hasAnyRole: (roles: readonly RoleName[]) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
