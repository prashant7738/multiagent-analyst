import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, FileCheck2, ShieldCheck, Workflow } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import AppNavbar from "@/components/AppNavbar";
import Button from "@/components/ui/button";

/**
 * GOAL: a stranger decides in under 30 seconds whether to trust this tool
 * with their data — then starts. The layout leads with the trust argument
 * (deterministic agents + validation gate); the one signature visual is a
 * static diagram of the actual pipeline. No idle motion anywhere.
 */

const STATS = [
  { value: "6", label: "Specialized agents, one pipeline" },
  { value: "95%", label: "Minimum confidence to ship a report" },
  { value: "0", label: "Spreadsheets you have to open" },
];

const FEATURES = [
  {
    icon: Workflow,
    title: "A pipeline, not a chatbot",
    body: "Six deterministic agents run in sequence on a LangGraph DAG. Each hands verified state to the next — same input, same analysis.",
  },
  {
    icon: FileCheck2,
    title: "Statistics before stories",
    body: "Descriptive stats, correlations, and trend regressions are computed with pandas, NumPy, and SciPy before any language model writes a word.",
  },
  {
    icon: ShieldCheck,
    title: "Nothing ships unvalidated",
    body: "A guardrail agent cross-checks every number against the source data. Below 0.95 confidence, the report is held back instead of guessed.",
  },
];

const STEPS = [
  { n: "01", title: "Upload a CSV", body: "Sales records, expenses, transactions — up to 100 MB." },
  { n: "02", title: "Agents run live", body: "Watch each stage complete with plain-language status." },
  { n: "03", title: "Read the results", body: "Executive summary first, evidence underneath it." },
  { n: "04", title: "Share the report", body: "Download a formatted PDF or HTML deliverable." },
];

const FAQ_ITEMS = [
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

function PipelineDiagram() {
  const stages = ["Profile", "Tag columns", "Clean data", "Compute & chart", "Validate", "Write report"];
  return (
    <div className="flex flex-wrap items-center gap-y-3" aria-label="Pipeline: six stages from profiling to report">
      {stages.map((label, i) => (
        <React.Fragment key={label}>
          <div
            className={`flex h-8 items-center rounded-full border px-3.5 text-xs font-medium ${
              i === 4 ? "border-accent bg-accent-subtle text-accent-ink" : "border-line bg-raised text-ink-secondary"
            }`}
          >
            {label}
          </div>
          {i < stages.length - 1 && <span className="mx-1.5 h-px w-4 bg-line-strong" aria-hidden="true" />}
        </React.Fragment>
      ))}
    </div>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const primaryTo = user ? "/analyze" : "/signup";

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <AppNavbar />

      {/* Hero: split layout, fits viewport, headline ≤ 2 lines */}
      <section className="mx-auto flex min-h-[calc(100dvh-4rem)] max-w-6xl flex-col justify-center px-6 py-20">
        <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.18em] text-ink-faint">
              CSV in · decision-ready report out
            </p>
            <h1 className="font-heading text-4xl font-bold tracking-tight text-ink sm:text-5xl lg:text-6xl">
              Your data, analyzed end-to-end before your coffee cools.
            </h1>
            <p className="mt-5 max-w-[52ch] text-lg leading-relaxed text-ink-muted">
              Upload a CSV. Six specialized agents clean, compute, visualize, and validate — then hand you a report you can defend.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" onClick={() => navigate(primaryTo)}>
                Start analyzing <ArrowRight size={16} aria-hidden="true" />
              </Button>
              <Button variant="secondary" size="lg" as="a" href="#how-it-works">
                See how it works
              </Button>
            </div>

            <dl className="mt-12 grid grid-cols-3 gap-6 border-t border-line pt-8">
              {STATS.map((s) => (
                <div key={s.label}>
                  <dd className="tnum font-heading text-3xl font-bold text-ink">{s.value}</dd>
                  <dd className="mt-1 text-xs leading-snug text-ink-faint">{s.label}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="rounded-panel border border-line bg-surface p-6">
            <p className="mb-5 text-xs font-semibold uppercase tracking-[0.18em] text-ink-faint">
              What runs when you press Analyze
            </p>
            <PipelineDiagram />
            <div className="mt-6 space-y-3 border-t border-line pt-5 text-sm leading-relaxed text-ink-muted">
              <p className="flex gap-2.5">
                <ShieldCheck size={16} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
                Every claim is checked against computed facts before it reaches you.
              </p>
              <p className="flex gap-2.5">
                <FileCheck2 size={16} className="mt-0.5 shrink-0 text-accent-ink" aria-hidden="true" />
                The full audit trail ships inside the downloadable report.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features: exactly 3 cells for 3 items */}
      <section id="features" className="border-t border-line py-24">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="font-heading text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Built to be trusted, not admired.
          </h2>
          <p className="mt-3 max-w-[60ch] text-lg text-ink-muted">
            Analysis you act on needs to be explainable. Each stage is deterministic, validated, and auditable.
          </p>
          <div className="mt-12 grid gap-px overflow-hidden rounded-panel border border-line bg-line md:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="bg-canvas p-7">
                <f.icon size={20} strokeWidth={1.75} className="text-accent-ink" aria-hidden="true" />
                <h3 className="mt-4 font-heading text-lg font-semibold text-ink">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-t border-line py-24">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="font-heading text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Four steps. One report.
          </h2>
          <ol className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n} className="border-t-2 border-line-strong pt-5">
                <span className="tnum font-heading text-sm font-semibold text-accent-ink">{s.n}</span>
                <h3 className="mt-2 font-heading text-base font-semibold text-ink">{s.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{s.body}</p>
              </li>
            ))}
          </ol>
          <div className="mt-14">
            <Button size="lg" onClick={() => navigate(primaryTo)}>
              Start analyzing <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
            </Button>
          </div>
        </div>
      </section>

      {/* FAQ: native details/summary — accessible with zero JS */}
      <section id="faq" className="border-t border-line py-24">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="font-heading text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Questions, answered straight.
          </h2>
          <div className="mt-10 divide-y divide-line border-y border-line">
            {FAQ_ITEMS.map((item) => (
              <details key={item.q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-left font-heading text-base font-medium text-ink [&::-webkit-details-marker]:hidden">
                  {item.q}
                  <span aria-hidden="true" className="shrink-0 text-lg text-ink-faint transition-transform duration-200 group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-ink-muted">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-line py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 sm:flex-row">
          <span className="font-heading text-base font-bold tracking-tight text-ink">
            Analyze<span className="text-accent">AI</span>
          </span>
          <p className="text-xs text-ink-faint">
            © {new Date().getFullYear()} AnalyzeAI · Thapathali Campus, IOE, TU · Minor Project BCT 2080
          </p>
        </div>
      </footer>
    </div>
  );
}
