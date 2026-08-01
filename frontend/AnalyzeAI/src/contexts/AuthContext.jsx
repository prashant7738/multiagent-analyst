import React, { createContext, useContext, useState } from "react";

const AuthContext = createContext(null);

function normalizeUser(userData) {
  if (!userData) return null;
  if (String(userData.email || "").toLowerCase() === "demo@analyzeai.io") {
    return null;
  }
  return {
    ...userData,
    joinedDate: userData.joinedDate || userData.created_at || userData.createdAt || null,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem("analyzeai_user");
      const parsed = stored ? normalizeUser(JSON.parse(stored)) : null;
      if (!parsed && stored) {
        localStorage.removeItem("analyzeai_user");
      }
      return parsed;
    } catch {
      localStorage.removeItem("analyzeai_user");
      return null;
    }
  });

  const login = (userData) => {
    const normalized = normalizeUser(userData);
    setUser(normalized);
    localStorage.setItem("analyzeai_user", JSON.stringify(normalized));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("analyzeai_user");
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
