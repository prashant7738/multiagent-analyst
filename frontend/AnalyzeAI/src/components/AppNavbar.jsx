import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import ThemeToggle from "@/components/ThemeToggle";
import LLMHealthIndicator from "@/components/LLMHealthIndicator";
import Button from "@/components/ui/button";

const NAV_ITEMS = [
  { label: "Analyze", to: "/analyze" },
  { label: "History", to: "/history" },
];

/**
 * The single app header. Auth state decides the right side; nothing else.
 * Plain links (no spotlight effects) — navigation is used too often to animate.
 */
export default function AppNavbar() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const close = () => setMenuOpen(false);

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-6">
        {/* Wordmark — static type, no gradient/glow */}
        <button
          onClick={() => navigate("/")}
          className="shrink-0 cursor-pointer font-heading text-lg font-bold tracking-tight text-ink"
        >
          Analyze<span className="text-accent">AI</span>
        </button>

        <nav className="hidden flex-1 items-center gap-1 md:flex" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-(--radius-control) px-3 py-2 text-sm transition-colors duration-150 ${
                  isActive ? "bg-raised text-ink" : "text-ink-muted hover:text-ink"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <LLMHealthIndicator />
          <ThemeToggle />

          {user ? (
            <>
              <button
                onClick={() => navigate("/profile")}
                className="pressable hidden items-center gap-2 rounded-full border border-line py-1 pl-1 pr-3 sm:flex"
                title={`${user.name} (${user.email})`}
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">
                  {user.name?.[0]?.toUpperCase() ?? "U"}
                </span>
                <span className="text-sm text-ink-secondary">{user.name?.split(" ")[0]}</span>
              </button>
              <Button variant="secondary" size="sm" onClick={() => { logout(); navigate("/"); }}>
                Log out
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" onClick={() => navigate("/login")}>
                Log in
              </Button>
              <Button size="sm" onClick={() => navigate("/signup")}>
                Sign up
              </Button>
            </>
          )}

          <button
            onClick={() => setMenuOpen((o) => !o)}
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            className="rounded-(--radius-control) p-2 text-ink-muted hover:bg-raised hover:text-ink md:hidden"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              {menuOpen ? (
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              ) : (
                <path fillRule="evenodd" d="M3 5a1 1 0 011-1h14a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h14a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h14a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav className="border-t border-line px-6 py-3 md:hidden" aria-label="Mobile">
          <div className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={close}
                className="rounded-(--radius-control) px-3 py-2.5 text-sm text-ink-secondary hover:bg-raised hover:text-ink"
              >
                {item.label}
              </NavLink>
            ))}
            {user && (
              <NavLink
                to="/profile"
                onClick={close}
                className="rounded-(--radius-control) px-3 py-2.5 text-sm text-ink-secondary hover:bg-raised hover:text-ink"
              >
                Profile
              </NavLink>
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
