import axios, { AxiosError } from "axios";
import { authStorage } from "./authStorage";
import { env } from "./env";

export const api = axios.create({
  baseURL: env.apiBaseUrl,
  headers: { "Content-Type": "application/json", Accept: "application/json" },
});

let unauthorizedHandler: (() => void) | undefined;
export function setUnauthorizedHandler(handler: (() => void) | undefined): void {
  unauthorizedHandler = handler;
}

api.interceptors.request.use((config) => {
  const token = authStorage.getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    authStorage.clearToken();
    unauthorizedHandler?.();
  }
  return Promise.reject(error);
});

export function getApiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (!(error instanceof AxiosError)) return fallback;
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" && detail.trim() ? detail : fallback;
}

export function getApiStatus(error: unknown): number | undefined {
  return error instanceof AxiosError ? error.response?.status : undefined;
}
