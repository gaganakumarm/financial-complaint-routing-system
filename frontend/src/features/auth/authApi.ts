import { api } from "../../lib/api";
import type { LoginCredentials, TokenResponse, User } from "./types";

export async function loginUser(credentials: LoginCredentials): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", credentials);
  return data;
}

export async function getCurrentUser(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}
