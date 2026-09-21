import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";

export const TOKEN_KEY = "shopflow.tokens";
export const STORE_KEY = "shopflow.store";

export function readTokens() {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeTokens(tokens) {
  try {
    if (tokens) localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage can be unavailable in private mode */
  }
}

export function readStoreId() {
  try {
    return localStorage.getItem(STORE_KEY) || null;
  } catch {
    return null;
  }
}

export function writeStoreId(storeId) {
  try {
    if (storeId) localStorage.setItem(STORE_KEY, String(storeId));
    else localStorage.removeItem(STORE_KEY);
  } catch {
    /* ignore */
  }
}

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const tokens = readTokens();
  if (tokens?.access) {
    config.headers.Authorization = `Bearer ${tokens.access}`;
  }
  const storeId = readStoreId();
  if (storeId && !config.headers["X-Store-Id"]) {
    config.headers["X-Store-Id"] = storeId;
  }
  return config;
});

let refreshing = null;

async function refreshAccessToken() {
  const tokens = readTokens();
  if (!tokens?.refresh) throw new Error("no refresh token");

  const { data } = await axios.post(`${BASE_URL}/auth/refresh/`, {
    refresh: tokens.refresh,
  });
  const next = { access: data.access, refresh: data.refresh || tokens.refresh };
  writeTokens(next);
  return next.access;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;

    const isAuthCall = original?.url?.includes("/auth/login") ||
      original?.url?.includes("/auth/refresh");

    if (status === 401 && !original?._retried && !isAuthCall) {
      original._retried = true;
      try {
        refreshing = refreshing || refreshAccessToken();
        const access = await refreshing;
        refreshing = null;
        original.headers.Authorization = `Bearer ${access}`;
        return api(original);
      } catch {
        refreshing = null;
        writeTokens(null);
        writeStoreId(null);
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  },
);

export function errorMessage(error, fallback = "Something went wrong.") {
  const payload = error?.response?.data;
  if (payload?.error?.message) return payload.error.message;
  if (payload?.detail) return payload.detail;
  if (typeof payload === "string") return payload;
  return fallback;
}

export function fieldErrors(error) {
  const details = error?.response?.data?.error?.details;
  if (!details || typeof details !== "object") return {};
  const out = {};
  for (const [key, value] of Object.entries(details)) {
    out[key] = Array.isArray(value) ? value[0] : String(value);
  }
  return out;
}

export function errorCode(error) {
  return error?.response?.data?.error?.code || null;
}
