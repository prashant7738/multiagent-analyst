import React, { createContext, useContext, useState } from "react";

/**
 * WARNING — WHAT THIS IS, AND IS NOT
 *
 * The backend (`POST /api/auth/login|signup`) verifies credentials against
 * PostgreSQL but issues **no token, session cookie, or auth header**, and all
 * `/api/*` data routes are currently unauthenticated. This context is therefore
 * a **UI-level identity hint**: it remembers who signed in so the interface can
 * personalize itself and route-guard private screens.
 *
 * It is NOT security. Route guards below prevent *accidental* exposure (e.g.
 * an anonymous visitor landing on /history), but nothing stops a crafted
 * request to the API. When the backend grows real sessions, this store should
 * hold that credential and attach it in lib/api.js — until then, do not present
 * this as account security anywhere in the UI.
 */
const AuthContext = createContext(null);

const STORAGE_KEY = "analyzeai_user";

function readStoredUser() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser);

  const login = (userData) => {
    setUser(userData ?? null);
    try {
      if (userData) localStorage.setItem(STORAGE_KEY, JSON.stringify(userData));
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable — session stays in memory only */
    }
  };

  const logout = () => {
    setUser(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
