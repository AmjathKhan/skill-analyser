import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

const ACCESS_TOKEN_KEY = "asa.access_token";
const REFRESH_TOKEN_KEY = "asa.refresh_token";

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  save(access: string, refresh: string) {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.access;
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  // FormData must keep the browser-generated multipart boundary. A default
  // application/json Content-Type (or multipart without a boundary) makes
  // FastAPI reject PDF/DOCX uploads as if no files were sent.
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    config.headers.delete("Content-Type");
  }
  return config;
});

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStore.refresh;
  if (!refresh) return null;
  try {
    const response = await axios.post(`${API_BASE_URL}/refresh`, { refresh_token: refresh });
    tokenStore.save(response.data.access_token, response.data.refresh_token);
    return response.data.access_token as string;
  } catch {
    tokenStore.clear();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as RetriableConfig | undefined;
    const status = error.response?.status ?? 0;

    // A single transparent refresh attempt keeps long sessions alive.
    const isAuthCall = config?.url?.includes("/login") || config?.url?.includes("/refresh");
    if (status === 401 && config && !config._retried && !isAuthCall && tokenStore.refresh) {
      config._retried = true;
      refreshInFlight = refreshInFlight ?? refreshAccessToken();
      const token = await refreshInFlight;
      refreshInFlight = null;
      if (token) {
        config.headers.set("Authorization", `Bearer ${token}`);
        return api.request(config);
      }
      window.dispatchEvent(new CustomEvent("asa:session-expired"));
    }

    const body = error.response?.data;
    throw new ApiError(
      status,
      body?.error?.code ?? "network_error",
      body?.error?.message ?? error.message ?? "Something went wrong",
      body?.error?.details,
    );
  },
);

export function downloadBlob(data: Blob, filename: string): void {
  const url = window.URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
