// Single source of truth for where the signed-in user's identity and bearer
// token live in localStorage. Shared by AuthContext (writes on login/logout)
// and api.js (reads to attach the Authorization header) to avoid the two
// modules importing each other.
export const USER_STORAGE_KEY = "analyzeai_user";
export const TOKEN_STORAGE_KEY = "analyzeai_token";

export function readStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeStoredToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* storage unavailable — session stays in memory only */
  }
}

export function clearStoredAuth() {
  try {
    localStorage.removeItem(USER_STORAGE_KEY);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
