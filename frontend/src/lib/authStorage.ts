const ACCESS_TOKEN_KEY = "fcrs.access-token";

export const authStorage = {
  getToken(): string | null {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY)?.trim();
    return token || null;
  },
  setToken(token: string): void {
    const normalized = token.trim();
    if (!normalized) throw new Error("Access token cannot be blank.");
    localStorage.setItem(ACCESS_TOKEN_KEY, normalized);
  },
  clearToken(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  },
};
