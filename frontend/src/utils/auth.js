const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const USER_KEY = "plagioscale_user_email";
const TOKEN_KEY = "plagioscale_access_token";
let refreshPromise = null;
function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function deleteCookie(name) {
  document.cookie = `${name}=; max-age=0; path=/`;
}

function decodeJwtPayload(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    return JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

export function isTokenExpired(token) {
  const payload = decodeJwtPayload(token);
  if (!payload || !payload.exp) return true;
  return Date.now() >= payload.exp * 1000;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || getCookie("access_token") || "";
}

export function getStoredEmail() {
  return localStorage.getItem(USER_KEY) || "";
}

export function setToken(token, email = "") {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  }
  if (email) {
    localStorage.setItem(USER_KEY, email);
  }
  refreshPromise = null;
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  deleteCookie("access_token");
  deleteCookie("csrf_token");
  refreshPromise = null;
  fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" }).catch(() => {});
}

export async function fetchMe() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { credentials: "include" });
    if (!res.ok) return null;
    const data = await res.json();
    return data;
  } catch {
    return null;
  }
}

export async function refreshToken() {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        clearToken();
        return null;
      }
      return true;
    } catch {
      return null;
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export async function getAuthHeaders() {
  const token = getToken();
  const csrf = getCookie("csrf_token");
  const headers = {};
  if (token && !isTokenExpired(token)) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  return headers;
}

export function fetchOpts(opts = {}) {
  const token = getToken();
  const csrf = getCookie("csrf_token");
  return {
    credentials: "include",
    ...opts,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...(opts.headers || {}),
    },
  };
}
