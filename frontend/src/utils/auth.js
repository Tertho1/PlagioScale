const TOKEN_KEY = "plagioscale_access_token";
const USER_KEY = "plagioscale_user_email";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token, email = "") {
  localStorage.setItem(TOKEN_KEY, token);
  if (email) {
    localStorage.setItem(USER_KEY, email);
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredEmail() {
  return localStorage.getItem(USER_KEY) || "";
}

export function getAuthHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}