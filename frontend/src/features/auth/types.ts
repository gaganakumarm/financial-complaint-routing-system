export const roles = ["customer", "reviewer", "administrator"] as const;
export type RoleName = (typeof roles)[number];

export interface User {
  id: string;
  role_id: string;
  role_name: RoleName;
  email: string;
  full_name: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginCredentials { email: string; password: string }
export interface TokenResponse { access_token: string; token_type: "bearer" }
