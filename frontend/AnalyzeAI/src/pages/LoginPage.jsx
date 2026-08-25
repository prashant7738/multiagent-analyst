import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, ArrowRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { loginUser } from "@/lib/api";
import AppNavbar from "@/components/AppNavbar";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
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
      setError("Please fill in all fields");
      return;
    }
    setLoading(true);
    try {
      const response = await loginUser(form.email, form.password);
      login(response.user);
      const redirectTo = location.state?.from?.pathname || "/analyze";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.message || "Unable to sign in");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col">
      <AppNavbar />
      {/* Minimal accent line */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-amber-700 to-transparent opacity-30" />
      <div className="flex-1 flex items-center justify-center px-4 py-12">

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-md"
      >
        {/* Header */}
        <div className="mb-12">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="text-xs uppercase tracking-widest text-accent mb-6 font-mono"
          >
            Sign in
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="text-4xl font-serif font-bold mb-3 leading-tight"
          >
            Welcome back.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="text-ink-secondary text-sm"
          >
            Access your analysis workspace and continue where you left off.
          </motion.p>
        </div>

        {/* Form Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="border border-line p-8 mb-8"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Email Input */}
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4 }}
            >
              <label className="block text-sm font-medium text-ink mb-2">
                Email Address
              </label>
              <div className="relative flex items-center">
                <Mail className="absolute left-4 w-4 h-4 text-neutral-400 pointer-events-none" />
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 dark:focus:border-amber-600 focus:ring-2 focus:ring-amber-700/20 transition-all"
                  style={{ paddingLeft: "44px" }}
                />
              </div>
            </motion.div>

            {/* Password Input */}
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.5 }}
            >
              <label className="block text-sm font-medium text-ink mb-2">
                Password
              </label>
              <div className="relative flex items-center">
                <Lock className="absolute left-4 w-4 h-4 text-neutral-400 pointer-events-none" />
                <input
                  type="password"
                  name="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 dark:focus:border-amber-600 focus:ring-2 focus:ring-amber-700/20 transition-all"
                  style={{ paddingLeft: "44px" }}
                />
              </div>
            </motion.div>

            {/* Error Message */}
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-3 bg-danger-subtle border border-danger text-sm text-danger"
              >
                {error}
              </motion.div>
            )}

            {/* Forgot Password */}
            <div className="flex justify-end">
              <a href="/forgot-password" className="text-sm text-accent hover:text-accent font-medium transition-colors">
                Forgot password?
              </a>
            </div>

            {/* Submit Button */}
            <motion.button
              type="submit"
              disabled={loading}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              className="w-full py-3 px-4 bg-accent hover:bg-accent-hover text-white font-semibold rounded-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? "Signing in..." : "Sign In"}
              {!loading && <ArrowRight className="w-4 h-4" />}
            </motion.button>
          </form>
        </motion.div>

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 }}
          className="text-center text-sm"
        >
          <p className="text-ink-secondary mb-4">
            Don't have an account?{" "}
            <a href="/signup" className="text-accent hover:text-accent font-medium transition-colors">
              Create one
            </a>
          </p>
          <p className="text-xs text-ink-muted">
            By signing in, you agree to our{" "}
            <a href="#" className="underline hover:text-ink-secondary">
              Terms
            </a>
            {" "}and{" "}
            <a href="#" className="underline hover:text-ink-secondary">
              Privacy Policy
            </a>
          </p>
        </motion.div>
      </motion.div>
      </div>
    </div>
  );
}
