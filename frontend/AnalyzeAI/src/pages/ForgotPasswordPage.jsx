import React, { useState } from "react";
import { Link } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";

/**
 * GOAL: someone locked out needs a next step, even before a reset backend
 * exists. This page is honest: it explains the current path instead of
 * pretending to send an email that never goes out.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  return (
    <AppLayout size="content">
      <div className="mx-auto w-full max-w-sm py-16">
        <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">Reset your password</h1>

        {submitted ? (
          <div className="mt-6">
            <p className="text-sm leading-relaxed text-ink-muted">
              Password resets aren&apos;t automated yet. Contact the project team and we&apos;ll
              verify your identity and reset the account for{" "}
              <span className="text-ink">{email}</span>.
            </p>
            <Button variant="secondary" as={Link} to="/login" className="mt-6">
              Back to sign in
            </Button>
          </div>
        ) : (
          <>
            <p className="mt-2 text-sm text-ink-muted">
              Enter your account email. Automated resets are on the roadmap — for now we&apos;ll
              show you how to reach the team.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (email.includes("@")) setSubmitted(true);
              }}
              className="mt-8 flex flex-col gap-5"
              noValidate
            >
              <Field label="Email" htmlFor="fp-email">
                <input
                  id="fp-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  className={inputClass()}
                />
              </Field>
              <Button type="submit" disabled={!email.includes("@")} className="w-full">
                Continue
              </Button>
            </form>
            <p className="mt-6 text-center text-xs text-ink-faint">
              Remembered it?{" "}
              <Link to="/login" className="text-accent-ink hover:text-accent">
                Sign in
              </Link>
            </p>
          </>
        )}
      </div>
    </AppLayout>
  );
}
