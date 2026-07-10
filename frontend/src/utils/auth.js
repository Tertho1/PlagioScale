const TOKEN_KEY = "plagioscale_access_token";
const USER_KEY = "plagioscale_user_email";
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
let refreshPromise = null;

function decodePayload(token) {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

function isTokenExpiringSoon(token, marginSec = 300) {
  const payload = decodePayload(token);
  if (!payload || !payload.exp) return true;
  return Date.now() / 1000 > payload.exp - marginSec;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token, email = "") {
  localStorage.setItem(TOKEN_KEY, token);
  if (email) {
    localStorage.setItem(USER_KEY, email);
  }
  refreshPromise = null;
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  refreshPromise = null;
}

export function getStoredEmail() {
  return localStorage.getItem(USER_KEY) || "";
}

export async function refreshToken() {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const token = getToken();
    if (!token) return null;

    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        clearToken();
        return null;
      }
      const data = await res.json();
      setToken(data.access_token);
      return data.access_token;
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
  if (!token) return {};

  if (isTokenExpiringSoon(token, 300)) {
    const fresh = await refreshToken();
    if (fresh) {
      return { Authorization: `Bearer ${fresh}` };
    }
    return {};
  }

  return { Authorization: `Bearer ${token}` };
}