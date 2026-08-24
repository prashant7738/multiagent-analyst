import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { useAuth } from "@/contexts/AuthContext";
import { signupUser } from "@/lib/api";

/**
 * GOAL: create an account with minimum friction. Four honest fields, inline
 * validation, one submit. No marketing copy on a working surface.
 */
export default function SignupPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    setErrors((prev) => ({ ...prev, [e.target.name]: "" }));
  };

  const validate = () => {
    const e = {};
    if (!form.name.trim()) e.name = "Name is required.";
    if (!form.email.includes("@")) e.email = "Enter a valid email.";
    if (form.password.length < 8) e.password = "Use at least 8 characters.";
    if (form.password !== form.confirm) e.confirm = "Passwords do not match.";
    return e;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) {
      setErrors(errs);
      return;
    }
    setLoading(true);
    try {
      const response = await signupUser({ name: form.name, email: form.email, password: form.password });
      login(response.user);
      navigate("/analyze");
    } catch (err) {
      setErrors((prev) => ({ ...prev, email: err.message || "Unable to create account." }));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppLayout size="content">
      <div className="mx-auto w-full max-w-sm py-16">
        <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">Create your account</h1>
        <p className="mt-2 text-sm text-ink-muted">One account keeps every analysis and report in one place.</p>

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5" noValidate>
          <Field label="Full name" htmlFor="su-name" error={errors.name}>
            <input
              id="su-name"
              type="text"
              name="name"
              value={form.name}
              onChange={handleChange}
              autoComplete="name"
              className={inputClass({ invalid: errors.name })}
            />
          </Field>

          <Field label="Email" htmlFor="su-email" error={errors.email}>
            <input
              id="su-email"
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              placeholder="you@example.com"
              autoComplete="email"
              className={inputClass({ invalid: errors.email })}
            />
          </Field>

          <Field label="Password" htmlFor="su-password" error={errors.password} help="At least 8 characters.">
            <input
              id="su-password"
              type="password"
              name="password"
              value={form.password}
              onChange={handleChange}
              autoComplete="new-password"
              className={inputClass({ invalid: errors.password })}
            />
          </Field>

          <Field label="Confirm password" htmlFor="su-confirm" error={errors.confirm}>
            <input
              id="su-confirm"
              type="password"
              name="confirm"
              value={form.confirm}
              onChange={handleChange}
              autoComplete="new-password"
              className={inputClass({ invalid: errors.confirm })}
            />
          </Field>

          <Button type="submit" disabled={loading} className="w-full">
            {loading ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-faint">
          Already have an account?{" "}
          <Link to="/login" className="text-accent-ink hover:text-accent">
            Sign in
          </Link>
        </p>
      </div>
    </AppLayout>
  );
}
