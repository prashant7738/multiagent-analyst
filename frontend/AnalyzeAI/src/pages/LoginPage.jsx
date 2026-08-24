import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { useAuth } from "@/contexts/AuthContext";
import { loginUser } from "@/lib/api";

/**
 * GOAL: return, authenticate, get back to work in one screen. A centered,
 * chrome-free form is the fastest possible path; everything else competes
 * with the task.
 */
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
      setError("Please fill in all fields.");
      return;
    }
    setLoading(true);
    try {
      const response = await loginUser(form.email, form.password);
      login(response.user);
      const redirectTo = location.state?.from?.pathname || "/analyze";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.message || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppLayout size="content">
      <div className="mx-auto w-full max-w-sm py-16">
        <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">Welcome back</h1>
        <p className="mt-2 text-sm text-ink-muted">Sign in to reach your analyses and reports.</p>

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5" noValidate>
          <Field label="Email" htmlFor="login-email">
            <input
              id="login-email"
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              placeholder="you@example.com"
              autoComplete="email"
              className={inputClass()}
            />
          </Field>

          <Field label="Password" htmlFor="login-password">
            <div className="flex items-center justify-between">
              <span />
              <Link to="/forgot-password" className="text-xs text-accent-ink hover:text-accent">
                Forgot password?
              </Link>
            </div>
            <input
              id="login-password"
              type="password"
              name="password"
              value={form.password}
              onChange={handleChange}
              placeholder="••••••••"
              autoComplete="current-password"
              className={inputClass()}
            />
          </Field>

          {error && (
            <p role="alert" className="rounded-(--radius-control) border border-danger bg-danger-subtle px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}

          <Button type="submit" disabled={loading} className="w-full">
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-faint">
          No account yet?{" "}
          <Link to="/signup" className="text-accent-ink hover:text-accent">
            Create one
          </Link>
        </p>
      </div>
    </AppLayout>
  );
}
