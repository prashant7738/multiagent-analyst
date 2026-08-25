import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, ChevronDown } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import AppNavbar from "@/components/AppNavbar";

export default function LandingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [faqOpen, setFaqOpen] = useState(null);

  const faqItems = [
    {
      q: "What kind of data does AnalyzeAI accept?",
      a: "CSV files with structured business data — sales records, transaction logs, expense sheets, inventory data, financial statements. Column types and semantics are detected automatically.",
    },
    {
      q: "How does the multi-agent pipeline work?",
      a: "Six agents run in sequence: Structural Profiler, Semantic Tagger, Preprocessor, Statistics & Visualization, Quality Guardrail, and Report Assembly. Each hands verified state to the next.",
    },
    {
      q: "How does it prevent hallucinated insights?",
      a: "The LLM never interprets raw data. It only receives validated statistical summaries produced by deterministic agents, and a guardrail enforces a confidence threshold of at least 0.95 before any insight reaches the report.",
    },
    {
      q: "What does the final report look like?",
      a: "A formatted PDF or HTML document with an executive summary, statistical tables, generated charts, plain-language insights, and recommendations — ready to share.",
    },
    {
      q: "Do I need any technical skills?",
      a: "None. Upload a CSV, press Analyze, and read the report. Cleaning, statistics, visualization, and writing all happen automatically.",
    },
    {
      q: "Is my uploaded data stored permanently?",
      a: "Uploaded files are processed for your analysis session. Don't upload anything you aren't authorized to analyze — this is a tool, not long-term storage.",
    },
  ];

  const steps = [
    { n: "01", title: "Upload a CSV", body: "Sales records, expenses, transactions — up to 100 MB." },
    { n: "02", title: "Agents run live", body: "Watch each stage complete with plain-language status." },
    { n: "03", title: "Read the results", body: "Executive summary first, evidence underneath it." },
    { n: "04", title: "Share the report", body: "Download a formatted PDF or HTML deliverable." },
  ];

  return (
    <div className="bg-canvas text-ink">
      <AppNavbar />

      {/* ─── HERO SECTION ─── */}
      <section className="min-h-screen flex items-center pt-24 pb-24 px-4 md:px-8">
        <div className="max-w-5xl mx-auto w-full">
          {/* Marginalia */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="mb-8 text-xs tracking-widest uppercase text-accent"
          >
            <span className="opacity-50">v1.0.0</span>
            <span className="mx-2 opacity-30">·</span>
            <span className="opacity-50">Deterministic Analysis</span>
            <span className="mx-2 opacity-30">·</span>
            <span className="opacity-50">LLM Pipeline</span>
          </motion.div>

          {/* Main Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1 }}
            className="text-5xl md:text-7xl leading-tight mb-6 font-serif font-bold"
          >
            CSV in.<br />
            Decision-ready<br />
            report out.
          </motion.h1>

          {/* Subheading */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="text-lg md:text-xl text-ink-secondary max-w-2xl mb-8 leading-relaxed"
          >
            For teams that understand their data. A small unfair advantage: six deterministic agents validate every number before a word reaches the report.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
            className="flex gap-4 flex-wrap"
          >
            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate(user ? "/analyze" : "/login")}
              className="px-8 py-3 bg-amber-700 hover:bg-amber-800 text-white font-medium text-base flex items-center gap-2 transition-all"
            >
              Get Started
              <ArrowRight className="w-4 h-4" />
            </motion.button>

            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate("/login")}
              className="px-8 py-3 border border-line text-ink hover:bg-raised font-medium text-base transition-all"
            >
              Learn More
            </motion.button>
          </motion.div>

          {/* Technical specs marginalia */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-16 pt-8 border-t border-line flex flex-wrap gap-8 text-xs"
          >
            <div>
              <div className="text-accent font-mono text-xs mb-1">6 AGENTS</div>
              <div className="text-ink-secondary">Specialized pipeline, not a chatbot</div>
            </div>
            <div>
              <div className="text-accent font-mono text-xs mb-1">95% CONFIDENCE</div>
              <div className="text-ink-secondary">Minimum threshold to ship</div>
            </div>
            <div>
              <div className="text-accent font-mono text-xs mb-1">DETERMINISTIC</div>
              <div className="text-ink-secondary">Same input, same result</div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─── HOW IT WORKS ─── */}
      <section className="py-24 px-4 md:px-8 border-t border-line">
        <div className="max-w-5xl mx-auto w-full">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-4xl md:text-5xl font-serif font-bold mb-4"
          >
            The pipeline.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-ink-secondary text-lg mb-12 max-w-2xl"
          >
            No guessing. No hallucinations. Six deterministic agents run in sequence on a LangGraph DAG. Each hands verified state to the next.
          </motion.p>

          {/* Steps Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {steps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: i * 0.1 }}
                viewport={{ once: true }}
                className="border border-line p-8"
              >
                <div className="text-accent text-sm font-mono font-bold mb-3 opacity-60">
                  {step.n}
                </div>
                <h3 className="text-xl font-serif font-bold mb-3">{step.title}</h3>
                <p className="text-ink-secondary text-sm">{step.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FEATURES ─── */}
      <section className="py-24 px-4 md:px-8 border-t border-line bg-neutral-50 dark:bg-neutral-900">
        <div className="max-w-5xl mx-auto w-full">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-4xl md:text-5xl font-serif font-bold mb-4"
          >
            Built for precision.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-ink-secondary text-lg mb-12 max-w-2xl"
          >
            Every number validated. Every insight grounded in statistics, not speculation.
          </motion.p>

          <div className="space-y-8">
            {[
              {
                title: "A pipeline, not a chatbot",
                body: "Six deterministic agents run in sequence on a LangGraph DAG. Each hands verified state to the next — same input, same analysis.",
              },
              {
                title: "Statistics before stories",
                body: "Descriptive stats, correlations, and trend regressions are computed with pandas, NumPy, and SciPy before any language model writes a word.",
              },
              {
                title: "Nothing ships unvalidated",
                body: "A guardrail agent cross-checks every number against the source data. Below 0.95 confidence, the report is held back instead of guessed.",
              },
            ].map((feature, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.6, delay: i * 0.1 }}
                viewport={{ once: true }}
                className="border border-line p-8"
              >
                <h3 className="text-2xl font-serif font-bold mb-3">{feature.title}</h3>
                <p className="text-ink-secondary">{feature.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section className="py-24 px-4 md:px-8 border-t border-line">
        <div className="max-w-3xl mx-auto w-full">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-4xl md:text-5xl font-serif font-bold mb-12"
          >
            Questions.
          </motion.h2>

          <div className="space-y-4">
            {faqItems.map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: i * 0.05 }}
                viewport={{ once: true }}
                className="border border-line"
              >
                <button
                  onClick={() => setFaqOpen(faqOpen === i ? null : i)}
                  className="w-full px-8 py-6 flex items-start justify-between gap-4 hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors"
                >
                  <h3 className="text-left font-serif text-lg font-bold">{item.q}</h3>
                  <motion.div
                    animate={{ rotate: faqOpen === i ? 180 : 0 }}
                    transition={{ duration: 0.3 }}
                    className="flex-shrink-0 mt-1"
                  >
                    <ChevronDown className="w-5 h-5 text-accent" />
                  </motion.div>
                </button>

                <motion.div
                  animate={{ height: faqOpen === i ? "auto" : 0 }}
                  transition={{ duration: 0.3 }}
                  className="overflow-hidden"
                >
                  <p className="px-8 pb-6 text-ink-secondary border-t border-line pt-6">
                    {item.a}
                  </p>
                </motion.div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FOOTER CTA ─── */}
      <section className="py-24 px-4 md:px-8 border-t border-line">
        <div className="max-w-3xl mx-auto w-full text-center">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
            className="text-4xl md:text-5xl font-serif font-bold mb-6"
          >
            Ready to analyze.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            viewport={{ once: true }}
            className="text-ink-secondary text-lg mb-8"
          >
            Upload your CSV. Let the pipeline work. Get actionable intelligence.
          </motion.p>

          <motion.button
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            viewport={{ once: true }}
            onClick={() => navigate(user ? "/analyze" : "/login")}
            className="px-8 py-4 bg-amber-700 hover:bg-amber-800 text-white font-semibold text-lg flex items-center gap-2 mx-auto transition-all"
          >
            Start Now
            <ArrowRight className="w-5 h-5" />
          </motion.button>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="border-t border-line py-12 px-4 md:px-8">
        <div className="max-w-5xl mx-auto w-full">
          <div className="flex flex-col md:flex-row justify-between items-center gap-8 text-sm text-ink-secondary">
            <div>
              <div className="font-serif font-bold text-neutral-900 dark:text-white mb-1">AnalyzeAI</div>
              <div className="text-xs">Deterministic data analysis. No speculation.</div>
            </div>
            <div className="flex gap-8">
              <a href="#" className="hover:text-neutral-900 dark:hover:text-white transition-colors">
                Docs
              </a>
              <a href="#" className="hover:text-neutral-900 dark:hover:text-white transition-colors">
                GitHub
              </a>
              <a href="#" className="hover:text-neutral-900 dark:hover:text-white transition-colors">
                Status
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
