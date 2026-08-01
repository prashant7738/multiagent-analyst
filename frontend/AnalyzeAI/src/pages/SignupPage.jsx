import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import AppNavbar from "@/components/AppNavbar";
import { GlowBorderCard } from "@/components/ui/glow-border-card";
import { CandyButton } from "@/components/ui/candy-button";
import { FlipText } from "@/components/ui/flip-text";
import { useAuth } from "@/contexts/AuthContext";
import { signupUser } from "@/lib/api";

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
    if (form.password.length < 8) e.password = "Password must be at least 8 characters.";
    if (form.password !== form.confirm) e.confirm = "Passwords do not match.";
    return e;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setLoading(true);
    try {
      const response = await signupUser({ name: form.name, email: form.email, password: form.password });
      login(response.user);
      navigate("/profile");
    } catch (err) {
      setErrors((prev) => ({ ...prev, email: err.message || "Unable to create account." }));
    } finally {
      setLoading(false);
    }
  };

  const fields = [
    { id: "name",     label: "Full Name",       type: "text",     placeholder: "Roshan Poudel",        autocomplete: "name" },
    { id: "email",    label: "Email Address",   type: "email",    placeholder: "you@example.com",      autocomplete: "email" },
    { id: "password", label: "Password",        type: "password", placeholder: "Min 8 characters",     autocomplete: "new-password" },
    { id: "confirm",  label: "Confirm Password",type: "password", placeholder: "Repeat your password", autocomplete: "new-password" },
  ];

  return (
    <div className="dark min-h-screen bg-black font-sans antialiased text-white">
      {/* Consistent ambient background */}
      <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-225 h-125 bg-radial-[ellipse_at_top] from-violet-950/25 via-transparent to-transparent" />
        <div className="page-grid absolute inset-0 opacity-40" />
      </div>

      <AppNavbar />

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] px-6 py-12">
        <div className="w-full max-w-lg">
          <div className="text-center mb-8">
            <FlipText
              className="text-5xl font-black text-white tracking-tight"
              duration={2.5}
              loop={false}
            >
              Get Started
            </FlipText>
            <p className="text-white/40 text-sm mt-3">
              Create your free account and start analyzing your data today.
            </p>
          </div>

          <GlowBorderCard
            colorPreset="ocean"
            width="100%"
            height="auto"
            aspectRatio="unset"
            borderWidth="0.5em"
            blurAmount="0.5em"
            animationDuration={6}
            className="bg-[#0a0a0a]"
          >
            <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-5">
              {fields.map(({ id, label, type, placeholder, autocomplete }) => (
                <div key={id} className="flex flex-col gap-2">
                  <label className="text-white/50 text-xs font-semibold tracking-widest uppercase">
                    {label}
                  </label>
                  <input
                    type={type}
                    name={id}
                    value={form[id]}
                    onChange={handleChange}
                    placeholder={placeholder}
                    autoComplete={autocomplete}
                    className={`w-full bg-white/5 border rounded-xl px-4 py-3 text-white text-sm placeholder-white/20 outline-none transition-all duration-200 cursor-text
                      ${errors[id]
                        ? "border-red-500/50 bg-red-500/5 focus:border-red-500/70"
                        : "border-white/10 focus:border-cyan-500/60 focus:bg-cyan-500/5"
                      }`}
                  />
                  {errors[id] && (
                    <p className="text-red-400/80 text-xs">{errors[id]}</p>
                  )}
                </div>
              ))}

              <p className="text-white/20 text-xs leading-relaxed">
                By signing up you agree to our Terms of Service and Privacy Policy.
                Your data is encrypted and never sold.
              </p>

              <CandyButton
                type="submit"
                disabled={loading}
                className={`w-full mt-1 py-3.5 text-base ${loading ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
              >
                {loading ? "Creating account…" : "Create Account →"}
              </CandyButton>
            </form>
          </GlowBorderCard>

          <p className="text-center text-white/20 text-xs mt-6">
            Already have an account?{" "}
            <Link to="/login" className="text-violet-400 hover:text-violet-300 transition-colors cursor-pointer">
              Sign in instead
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
