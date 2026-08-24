import React from "react";
import AppNavbar from "@/components/AppNavbar";

/**
 * The single owner of page chrome: ambient background, container width,
 * and vertical rhythm. Every authenticated/auth-adjacent page renders inside
 * this; nothing else may add its own background layer.
 *
 * size: "content" (forms/reading) | "default" (most pages) | "wide" (tables)
 */
const CONTAINERS = {
  content: "max-w-[42rem]",
  default: "max-w-6xl",
  wide: "max-w-7xl",
};

export default function AppLayout({ children, size = "default", className = "" }) {
  return (
    <div className="min-h-dvh flex flex-col bg-canvas text-ink">
      {/* Ambient layer — static, quiet, identical on every inner page */}
      <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
        <div
          className="absolute inset-x-0 top-0 h-[480px]"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% -10%, var(--accent-subtle), transparent 70%)",
          }}
        />
        <div className="absolute inset-0 bg-dotgrid opacity-[0.35]" />
      </div>

      <AppNavbar />

      <main className={`relative z-10 flex-1 w-full mx-auto ${CONTAINERS[size]} px-6 py-12 ${className}`}>
        {children}
      </main>

      <footer className="relative z-10 border-t border-line py-6">
        <p className="text-center text-xs text-ink-faint">
          AnalyzeAI · Six-agent analysis pipeline
        </p>
      </footer>
    </div>
  );
}
