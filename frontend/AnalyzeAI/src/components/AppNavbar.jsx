import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { SpotlightNavbar } from "@/components/ui/spotlight-navbar";

const NAV_ITEMS = [
  { label: "Home",         href: "/" },
  { label: "Features",     href: "/#features" },
  { label: "How It Works", href: "/#howitworks" },
  { label: "History",      href: "/history" },
];

export default function AppNavbar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const go = (href) => {
    setMenuOpen(false);
    if (href.startsWith("/#")) {
      if (location.pathname !== "/") {
        navigate("/");
        setTimeout(() => {
          document.getElementById(href.slice(2))?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      } else {
        document.getElementById(href.slice(2))?.scrollIntoView({ behavior: "smooth" });
      }
    } else {
      navigate(href);
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-black/85 backdrop-blur-xl border-b border-white/6 shadow-[0_1px_0_rgba(139,92,246,0.12)]">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center gap-4">

        {/* Logo */}
        <button onClick={() => go("/")} className="shrink-0 cursor-pointer select-none w-40">
          <span className="logo-brand text-[1.35rem] font-black tracking-tight">AnalyzeAI</span>
        </button>

        {/* SpotlightNavbar for desktop links */}
        <div className="flex-1 hidden md:flex justify-center">
          <SpotlightNavbar
            items={NAV_ITEMS.map(l => ({ label: l.label, href: l.href }))}
            onItemClick={(item) => go(item.href)}
            defaultActiveIndex={Math.max(0, NAV_ITEMS.findIndex(item => item.href === location.pathname))}
          />
        </div>

        {/* Right side actions */}
        <div className="shrink-0 w-40 flex items-center justify-end gap-2.5">
          {user ? (
            <>
              <button onClick={() => navigate("/profile")}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 hover:border-violet-500/40 hover:bg-violet-500/5 transition-all duration-200 cursor-pointer group">
                <div className="w-6 h-6 rounded-full bg-violet-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {user.name?.[0]?.toUpperCase() ?? "U"}
                </div>
                <span className="text-white/70 text-sm group-hover:text-white transition-colors hidden sm:block">
                  {user.name?.split(" ")[0]}
                </span>
              </button>
              <button onClick={() => navigate("/analyze")}
                className="px-4 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors duration-200 cursor-pointer shadow-[0_0_14px_rgba(139,92,246,0.4)] whitespace-nowrap">
                Analyze →
              </button>
            </>
          ) : (
            <>
              {location.pathname !== "/login" && (
                <button onClick={() => navigate("/login")}
                  className="px-4 py-2 rounded-full border border-white/10 hover:border-white/30 text-white/60 hover:text-white text-sm transition-all duration-200 cursor-pointer whitespace-nowrap">
                  Log In
                </button>
              )}
              {location.pathname !== "/signup" && (
                <button onClick={() => navigate("/signup")}
                  className="px-4 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors duration-200 cursor-pointer shadow-[0_0_14px_rgba(139,92,246,0.4)] whitespace-nowrap">
                  Sign Up
                </button>
              )}
            </>
          )}

          {/* Mobile hamburger */}
          <button onClick={() => setMenuOpen(!menuOpen)}
            className="md:hidden p-2 rounded-lg text-white/40 hover:text-white hover:bg-white/5 transition-colors cursor-pointer">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              {menuOpen
                ? <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd"/>
                : <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd"/>
              }
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="md:hidden border-t border-white/5 bg-black/95 px-6 py-4 flex flex-col gap-1">
          {NAV_ITEMS.map((l) => (
            <button key={l.label} onClick={() => go(l.href)}
              className="text-left px-4 py-3 rounded-xl text-white/60 hover:text-white hover:bg-white/5 text-sm transition-colors cursor-pointer">
              {l.label}
            </button>
          ))}
          <div className="flex gap-2 pt-2 border-t border-white/5 mt-1">
            {user ? (
              <>
                <button onClick={() => { setMenuOpen(false); navigate("/profile"); }}
                  className="flex-1 py-2.5 rounded-xl border border-violet-500/30 text-violet-300 text-sm text-center transition-colors cursor-pointer">
                  Profile
                </button>
                <button onClick={() => { setMenuOpen(false); logout(); navigate("/"); }}
                  className="flex-1 py-2.5 rounded-xl border border-white/10 text-red-400/70 hover:text-red-400 text-sm text-center transition-colors cursor-pointer">
                  Log Out
                </button>
              </>
            ) : (
              <>
                <button onClick={() => { setMenuOpen(false); navigate("/login"); }}
                  className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/60 hover:text-white text-sm text-center transition-colors cursor-pointer">
                  Log In
                </button>
                <button onClick={() => { setMenuOpen(false); navigate("/signup"); }}
                  className="flex-1 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold text-center transition-colors cursor-pointer">
                  Sign Up
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
