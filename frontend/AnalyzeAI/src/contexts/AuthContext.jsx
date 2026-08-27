import React, { createContext, useContext, useState } from "react";
import { USER_STORAGE_KEY, TOKEN_STORAGE_KEY, readStoredToken, clearStoredAuth } from "../lib/authStorage";
import { logoutUser } from "../lib/api";

/**
 * The backend (`POST /api/auth/login|signup`) verifies credentials against
 * PostgreSQL and issues a bearer token backed by a server-side session record
 * (see `api/services/auth_store.py`). This context holds that identity + token
 * for the UI: it drives personalization, route-guards private screens, and
 * `logout()` both clears the local session and asks the backend to invalidate
 * the token so it can't be replayed.
 */
const AuthContext = createContext(null);

function readStoredUser() {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    localStorage.removeItem(USER_STORAGE_KEY);
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser);

  const login = (userData, token) => {
    setUser(userData ?? null);
    try {
      if (userData) localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));
      else localStorage.removeItem(USER_STORAGE_KEY);
      if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
      else localStorage.removeItem(TOKEN_STORAGE_KEY);
    } catch {
      /* storage unavailable — session stays in memory only */
    }
  };

  const logout = () => {
    const token = readStoredToken();
    setUser(null);
    clearStoredAuth();
    // Best-effort — the local session is already gone either way.
    logoutUser(token);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
