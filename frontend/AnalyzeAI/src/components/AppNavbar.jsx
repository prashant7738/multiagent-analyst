import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import ThemeToggle from "@/components/ThemeToggle";
import LLMHealthIndicator from "@/components/LLMHealthIndicator";

const NAV_ITEMS = [
  { label: "Home", to: "/" },
  { label: "Analyze", to: "/analyze" },
  { label: "History", to: "/history" },
];

export default function AppNavbar() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const close = () => setMenuOpen(false);

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-canvas backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-6">
        {/* Wordmark */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => navigate("/")}
          className="shrink-0 cursor-pointer font-serif text-lg font-bold tracking-tight text-ink"
        >
          Analyze<span className="text-accent">AI</span>
        </motion.button>

        {/* Desktop Navigation */}
        <nav className="hidden flex-1 items-center gap-8 md:flex" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `text-sm font-medium transition-colors relative ${
                  isActive
                    ? "text-accent"
                    : "text-ink-secondary hover:text-ink"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {item.label}
                  {isActive && (
                    <motion.div
                      layoutId="underline"
                      className="absolute -bottom-1 left-0 right-0 h-0.5 bg-accent"
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Right Section */}
        <div className="ml-auto flex shrink-0 items-center gap-4">
          <LLMHealthIndicator />
          <ThemeToggle />

          {user ? (
            <>
              {/* User Profile Button - Desktop */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate("/profile")}
                className="hidden items-center gap-2 px-3 py-2 border border-line rounded-sm text-sm font-medium hover:bg-raised transition-colors sm:flex text-ink"
                title={`${user.name} (${user.email})`}
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-sm bg-amber-700 text-xs font-bold text-white">
                  {user.name?.[0]?.toUpperCase() ?? "U"}
                </span>
                <span className="text-ink">
                  {user.name?.split(" ")[0]}
                </span>
              </motion.button>

              {/* Log Out Button */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => { logout(); navigate("/"); }}
                className="hidden px-4 py-2 text-sm font-medium border border-line text-ink hover:bg-raised rounded-sm transition-colors sm:block"
              >
                Log out
              </motion.button>
            </>
          ) : (
            <>
              {/* Log In Button */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate("/login")}
                className="hidden px-4 py-2 text-sm font-medium text-ink hover:bg-raised rounded-sm transition-colors sm:block"
              >
                Log in
              </motion.button>

              {/* Sign Up Button */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate("/signup")}
                className="hidden px-4 py-2 text-sm font-medium bg-accent hover:bg-accent-hover text-white rounded-sm transition-colors sm:block"
              >
                Sign up
              </motion.button>
            </>
          )}

          {/* Mobile Menu Button */}
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setMenuOpen((o) => !o)}
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            className="p-2 text-ink-secondary hover:text-ink md:hidden"
          >
            {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </motion.button>
        </div>
      </div>

      {/* Mobile Navigation */}
      <motion.nav
        animate={{ height: menuOpen ? "auto" : 0 }}
        transition={{ duration: 0.2 }}
        className="overflow-hidden border-t border-line md:hidden"
        aria-label="Mobile"
      >
        <div className="flex flex-col gap-1 px-6 py-4">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={close}
              className={({ isActive }) =>
                `px-3 py-2.5 text-sm font-medium rounded-sm transition-colors ${
                  isActive
                    ? "bg-raised text-accent"
                    : "text-ink-secondary hover:bg-raised"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}

          {user && (
            <>
              <NavLink
                to="/profile"
                onClick={close}
                className={({ isActive }) =>
                  `px-3 py-2.5 text-sm font-medium rounded-sm transition-colors ${
                    isActive
                      ? "bg-neutral-100 dark:bg-neutral-900 text-amber-700 dark:text-amber-600"
                      : "text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-900"
                  }`
                }
              >
                Profile
              </NavLink>

              <button
                onClick={() => { logout(); navigate("/"); close(); }}
                className="px-3 py-2.5 text-sm font-medium text-ink-secondary hover:bg-raised rounded-sm transition-colors text-left"
              >
                Log out
              </button>
            </>
          )}

          {!user && (
            <>
              <button
                onClick={() => { navigate("/login"); close(); }}
                className="px-3 py-2.5 text-sm font-medium text-ink-secondary hover:bg-raised rounded-sm transition-colors text-left"
              >
                Log in
              </button>
              <button
                onClick={() => { navigate("/signup"); close(); }}
                className="px-3 py-2.5 text-sm font-medium bg-accent hover:bg-accent-hover text-white rounded-sm transition-colors text-left"
              >
                Sign up
              </button>
            </>
          )}
        </div>
      </motion.nav>
    </header>
  );
}
