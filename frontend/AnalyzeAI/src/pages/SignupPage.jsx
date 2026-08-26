import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Mail, Lock, User, CheckCircle2, ArrowRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { signupUser } from "@/lib/api";
import AppNavbar from "@/components/AppNavbar";

export default function SignupPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    email: "",
    password: "",
    confirm: "",
    name: "",
    notifications: true,
  });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((f) => ({
      ...f,
      [name]: type === "checkbox" ? checked : value,
    }));
    setErrors((prev) => ({ ...prev, [name]: "" }));
  };

  const validateStep = (currentStep) => {
    const e = {};
    if (currentStep === 1) {
      if (!form.email.includes("@")) e.email = "Enter a valid email";
      if (form.password.length < 8) e.password = "At least 8 characters";
      if (form.password !== form.confirm) e.confirm = "Passwords don't match";
    }
    if (currentStep === 2) {
      if (!form.name.trim()) e.name = "Name is required";
    }
    return e;
  };

  const handleNextStep = () => {
    const errs = validateStep(step);
    if (Object.keys(errs).length) {
      setErrors(errs);
      return;
    }
    setStep(step + 1);
  };

  const handlePrevStep = () => {
    setStep(step - 1);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validateStep(step);
    if (Object.keys(errs).length) {
      setErrors(errs);
      return;
    }
    setLoading(true);
    try {
      const response = await signupUser({
        name: form.name,
        email: form.email,
        password: form.password,
      });
      login(response.user, response.token);
      setSuccess(true);
      setTimeout(() => navigate("/analyze"), 2000);
    } catch (err) {
      setErrors((prev) => ({ ...prev, email: err.message || "Sign up failed" }));
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
        transition={{ duration: 0.5 }}
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
            Step {step} of 3
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="text-4xl font-serif font-bold mb-3 leading-tight"
          >
            Create account.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="text-ink-secondary text-sm"
          >
            {step === 1 ? "Secure your account" : step === 2 ? "Tell us about you" : "Preferences"}
          </motion.p>

          {/* Progress bar */}
          <div className="mt-6 h-0.5 bg-line">
            <motion.div
              className="h-full bg-accent"
              animate={{ width: `${(step / 3) * 100}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>

        {/* Form Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="border border-line p-8"
        >
          <AnimatePresence mode="wait">
            {success ? (
              <motion.div
                key="success"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="text-center py-8"
              >
                <motion.div
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ duration: 0.6 }}
                  className="mb-4"
                >
                  <CheckCircle2 className="w-16 h-16 mx-auto text-green-600 dark:text-green-400" />
                </motion.div>
                <h2 className="text-2xl font-serif font-bold text-ink mb-2">Account created.</h2>
                <p className="text-ink-secondary mb-6 text-sm">Redirecting to workspace...</p>
              </motion.div>
            ) : (
              <form key="form" onSubmit={step === 3 ? handleSubmit : (e) => { e.preventDefault(); handleNextStep(); }} className="space-y-6">
                {/* Step 1: Email & Password */}
                {step === 1 && (
                  <motion.div
                    key="step1"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-5"
                  >
                    <div>
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
                          className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 focus:ring-2 focus:ring-amber-700/20 transition-all"
                          style={{ paddingLeft: "44px" }}
                        />
                      </div>
                      {errors.email && <p className="text-sm text-danger mt-1">{errors.email}</p>}
                    </div>

                    <div>
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
                          className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 focus:ring-2 focus:ring-amber-700/20 transition-all"
                          style={{ paddingLeft: "44px" }}
                        />
                      </div>
                      {errors.password && <p className="text-sm text-danger mt-1">{errors.password}</p>}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">
                        Confirm Password
                      </label>
                      <div className="relative flex items-center">
                        <Lock className="absolute left-4 w-4 h-4 text-neutral-400 pointer-events-none" />
                        <input
                          type="password"
                          name="confirm"
                          value={form.confirm}
                          onChange={handleChange}
                          placeholder="••••••••"
                          className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 focus:ring-2 focus:ring-amber-700/20 transition-all"
                          style={{ paddingLeft: "44px" }}
                        />
                      </div>
                      {errors.confirm && <p className="text-sm text-danger mt-1">{errors.confirm}</p>}
                    </div>
                  </motion.div>
                )}

                {/* Step 2: Profile */}
                {step === 2 && (
                  <motion.div
                    key="step2"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-5"
                  >
                    <div>
                      <label className="block text-sm font-medium text-ink mb-2">
                        Full Name
                      </label>
                      <div className="relative flex items-center">
                        <User className="absolute left-4 w-4 h-4 text-neutral-400 pointer-events-none" />
                        <input
                          type="text"
                          name="name"
                          value={form.name}
                          onChange={handleChange}
                          placeholder="John Doe"
                          className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 focus:ring-2 focus:ring-amber-700/20 transition-all"
                          style={{ paddingLeft: "44px" }}
                        />
                      </div>
                      {errors.name && <p className="text-sm text-danger mt-1">{errors.name}</p>}
                    </div>
                  </motion.div>
                )}

                {/* Step 3: Preferences */}
                {step === 3 && (
                  <motion.div
                    key="step3"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    className="space-y-4"
                  >
                    <label className="flex items-start gap-3 p-3 border border-line cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors">
                      <input
                        type="checkbox"
                        name="notifications"
                        checked={form.notifications}
                        onChange={handleChange}
                        className="w-4 h-4 rounded mt-1 cursor-pointer"
                      />
                      <div>
                        <p className="font-medium text-ink text-sm">Email Notifications</p>
                        <p className="text-xs text-ink-secondary mt-0.5">Get updates on your analyses</p>
                      </div>
                    </label>
                  </motion.div>
                )}

                {/* Buttons */}
                <div className="flex gap-3 pt-4">
                  {step > 1 && (
                    <motion.button
                      type="button"
                      onClick={handlePrevStep}
                      className="flex-1 py-3 px-4 bg-raised text-ink font-medium rounded-sm hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-all"
                      whileHover={{ y: -1 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      Back
                    </motion.button>
                  )}
                  <motion.button
                    type="submit"
                    disabled={loading}
                    className="flex-1 py-3 px-4 bg-accent hover:bg-amber-800 text-white font-semibold rounded-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                    whileHover={{ y: -1 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {loading ? "Creating..." : step === 3 ? "Create Account" : "Next"}
                    {!loading && step < 3 && <ArrowRight className="w-4 h-4" />}
                  </motion.button>
                </div>

                {errors.email && step === 3 && (
                  <div className="p-3 rounded-sm bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 text-sm text-red-700 dark:text-red-400">
                    {errors.email}
                  </div>
                )}
              </form>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Footer */}
        {!success && (
          <motion.div
            className="mt-8 text-center text-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            <p className="text-ink-secondary">
              Already have an account?{" "}
              <a href="/login" className="text-accent hover:text-accent font-medium transition-colors">
                Sign in
              </a>
            </p>
          </motion.div>
        )}
      </motion.div>
      </div>
    </div>
  );
}
