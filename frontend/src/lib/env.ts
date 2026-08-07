export function parseApiBaseUrl(value: string | undefined): string {
  const normalized = value?.trim().replace(/\/+$/, "");
  if (!normalized) {
    throw new Error("VITE_API_BASE_URL is required. Copy .env.example to .env.local.");
  }
  try {
    return new URL(normalized).toString().replace(/\/$/, "");
  } catch {
    throw new Error("VITE_API_BASE_URL must be a valid absolute URL.");
  }
}

const configuredUrl = import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.MODE === "test" ? "http://localhost:8000/api" : undefined);

export const env = Object.freeze({ apiBaseUrl: parseApiBaseUrl(configuredUrl) });
