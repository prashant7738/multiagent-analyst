import React, { useState } from "react";
import { Link } from "react-router-dom";
import AppNavbar from "@/components/AppNavbar";
import { CandyButton } from "@/components/ui/candy-button";
import { FlipText } from "@/components/ui/flip-text";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { loginUser } from "@/lib/api";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    setError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.email || !form.password) {
      setError("Please fill in all fields.");
      return;
    }
    setLoading(true);
    try {
      const response = await loginUser(form.email, form.password);
      login(response.user);
      navigate("/profile");
    } catch (err) {
      setError(err.message || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dark min-h-screen bg-black font-sans antialiased text-white">
      {/* Consistent ambient background — same visual language as landing page */}
      <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-225 h-125 bg-radial-[ellipse_at_top] from-violet-950/25 via-transparent to-transparent" />
        <div className="page-grid absolute inset-0 opacity-40" />
      </div>

      <AppNavbar />

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] px-6 py-12">
        <div className="w-full max-w-lg">
          {/* Heading */}
          <div className="text-center mb-8">
            <FlipText
              className="text-5xl font-black text-white tracking-tight"
              duration={2.5}
              loop={false}
            >
              Welcome Back
            </FlipText>
            <p className="text-white/40 text-sm mt-3">
              Sign in to access your analyses, reports, and history.
            </p>
          </div>

          {/* Form card */}
          <div className="w-full rounded-2xl border border-white/8 bg-[#0a0a0a] shadow-[0_0_60px_rgba(139,92,246,0.1)] ring-1 ring-violet-500/10">
            <form onSubmit={handleSubmit} className="w-full p-7 flex flex-col gap-5">
              {/* Email */}
              <div className="flex flex-col gap-2">
                <label className="text-white/50 text-xs font-semibold tracking-widest uppercase">
                  Email Address
                </label>
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  autoComplete="email"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-sm placeholder-white/20 outline-none focus:border-violet-500/60 focus:bg-violet-500/5 transition-all duration-200 cursor-text"
                />
              </div>

              {/* Password */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-white/50 text-xs font-semibold tracking-widest uppercase">
                    Password
                  </label>
                  <Link to="/forgot-password" className="text-violet-400/60 hover:text-violet-400 text-xs transition-colors cursor-pointer">
                    Forgot password?
                  </Link>
                </div>
                <input
                  type="password"
                  name="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-sm placeholder-white/20 outline-none focus:border-violet-500/60 focus:bg-violet-500/5 transition-all duration-200 cursor-text"
                />
              </div>

              {/* Error */}
              {error && (
                <p className="text-red-400/80 text-xs bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              {/* Submit */}
              <CandyButton
                type="submit"
                disabled={loading}
                className={`w-full mt-1 py-3.5 text-base ${loading ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
              >
                {loading ? "Signing in…" : "Sign In →"}
              </CandyButton>
            </form>
          </div>

          <p className="text-center text-white/20 text-xs mt-6">
            Don&apos;t have an account?{" "}
            <Link to="/signup" className="text-violet-400 hover:text-violet-300 transition-colors cursor-pointer">
              Create one free
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
