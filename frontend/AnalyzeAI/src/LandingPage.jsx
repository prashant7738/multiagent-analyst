import React from "react";
import { useNavigate } from "react-router-dom";
import { SpotlightNavbar } from "@/components/ui/spotlight-navbar";
import { PerspectiveGrid } from "@/components/ui/perspective-grid";
import { MorphText } from "@/components/ui/morph-text";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { GlowBorderCard } from "@/components/ui/glow-border-card";
import { FaqAccordion } from "@/components/ui/faq-accordion";
import AnimatedButton from "@/components/ui/animated-button";
import { useAuth } from "@/contexts/AuthContext";

const NAV_ITEMS = [
  { label: "Home",         href: "/" },
  { label: "Features",     href: "#features" },
  { label: "How It Works", href: "#howitworks" },
  { label: "FAQ",          href: "#faq" },
  { label: "History",      href: "/history" },
];

const STATS = [
  { value: 90, label: "Faster than manual analysis", suffix: "%" },
  { value: 6,  label: "Specialized AI Agents",        suffix: "" },
  { value: 95, label: "Output Validation Threshold",  suffix: "%" },
];

const FAQ_ITEMS = [
  {
    question: "What kind of data does AnalyzeAI accept?",
    answer: "AnalyzeAI accepts CSV files containing structured business data — sales records, transaction logs, expense sheets, inventory data, and financial statements. The system automatically detects column types and semantics.",
  },
  {
    question: "How does the multi-agent pipeline work?",
    answer: "Six specialized agents run in sequence: a Structural Profiler, a Semantic Tagging agent, a Preprocessing agent, a Visualization & Statistics agent, an Output Validation agent, and a Report Assembly agent. Each agent hands verified state to the next.",
  },
  {
    question: "How does it prevent hallucinated insights?",
    answer: "The LLM never interprets raw data. It only receives validated statistical summaries (means, growth rates, correlations) produced by deterministic agents. A Quality Guardrail agent enforces a confidence threshold of >= 0.95 before any insight reaches the report.",
  },
  {
    question: "What does the final report look like?",
    answer: "You receive a professionally formatted PDF or HTML report with a dataset summary, statistical analysis tables, auto-generated charts, plain-language insights, and actionable recommendations — ready to share with stakeholders.",
  },
  {
    question: "Do I need any technical skills?",
    answer: "None at all. Upload your CSV, click Analyze, and download the report. The entire pipeline — cleaning, statistics, visualization, insight writing — runs automatically.",
  },
  {
    question: "Is my uploaded data stored permanently?",
    answer: "No. Uploaded CSV files are processed in-session and are not stored permanently unless you explicitly save a project. All data is encrypted in transit (TLS 1.3) and at rest (AES-256).",
  },
];

function NetworkGraph() {
  const nodes = [
    { cx: 100, cy: 60 }, { cx: 180, cy: 30 }, { cx: 260, cy: 60 },
    { cx: 70, cy: 130 },  { cx: 180, cy: 110 },{ cx: 290, cy: 130 },
    { cx: 130, cy: 200 }, { cx: 230, cy: 200 },
  ];
  const edges = [[0,1],[1,2],[0,3],[1,4],[2,5],[3,4],[4,5],[3,6],[4,7],[5,7],[6,7]];
  return (
    <svg viewBox="0 0 360 240" className="w-full h-40" aria-hidden="true">
      <style>{`
        @keyframes edge-dash { to { stroke-dashoffset: -24; } }
        @keyframes node-pulse { 0%,100%{r:6;opacity:.9} 50%{r:9;opacity:1} }
        .net-edge { stroke-dasharray:6 6; animation:edge-dash 1.2s linear infinite; }
        .net-node { animation:node-pulse 2s ease-in-out infinite; }
      `}</style>
      {edges.map(([a,b],i) => (
        <line key={i} className="net-edge"
          x1={nodes[a].cx} y1={nodes[a].cy} x2={nodes[b].cx} y2={nodes[b].cy}
          stroke="rgba(139,92,246,0.5)" strokeWidth="1.5"
          style={{ animationDelay:`${i*0.1}s` }} />
      ))}
      {nodes.map((n,i) => (
        <circle key={i} className="net-node" cx={n.cx} cy={n.cy} r="6"
          fill={i===4?"#8b5cf6":"rgba(139,92,246,0.4)"}
          stroke="rgba(139,92,246,0.8)" strokeWidth="1.5"
          style={{ animationDelay:`${i*0.25}s` }} />
      ))}
    </svg>
  );
}

function BarChart() {
  const bars = [
    {h:60,d:"0s"},{h:110,d:"0.1s"},{h:80,d:"0.2s"},{h:140,d:"0.3s"},
    {h:95,d:"0.4s"},{h:165,d:"0.5s"},{h:120,d:"0.6s"},{h:150,d:"0.7s"},
  ];
  return (
    <svg viewBox="0 0 320 180" className="w-full h-40" aria-hidden="true">
      <style>{`
        @keyframes bar-grow { 0%,100%{transform:scaleY(1)} 50%{transform:scaleY(1.15)} }
        .bar-rect { transform-origin:bottom; animation:bar-grow 2s ease-in-out infinite; }
      `}</style>
      <line x1="20" y1="170" x2="300" y2="170" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
      {[40,80,120,160].map(y=>(
        <line key={y} x1="20" y1={y} x2="300" y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="1"/>
      ))}
      {bars.map((b,i)=>{
        const x=28+i*34; const gid=`bg${i}`;
        return (
          <g key={i}>
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={i%2===0?"#8b5cf6":"#06b6d4"} stopOpacity="0.9"/>
                <stop offset="100%" stopColor={i%2===0?"#6d28d9":"#0891b2"} stopOpacity="0.3"/>
              </linearGradient>
            </defs>
            <rect className="bar-rect" x={x} y={170-b.h} width="22" height={b.h}
              rx="3" fill={`url(#${gid})`} style={{animationDelay:b.d}}/>
          </g>
        );
      })}
    </svg>
  );
}

function LineChart() {
  const pts=[[20,140],[60,110],[100,125],[140,75],[180,90],[220,50],[260,65],[300,35]];
  const polyline=pts.map(p=>p.join(",")).join(" ");
  const area=`M${pts[0][0]},170 `+pts.map(p=>`L${p[0]},${p[1]}`).join(" ")+` L${pts[pts.length-1][0]},170 Z`;
  return (
    <svg viewBox="0 0 320 180" className="w-full h-40" aria-hidden="true">
      <defs>
        <linearGradient id="la-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.3"/>
          <stop offset="100%" stopColor="#06b6d4" stopOpacity="0"/>
        </linearGradient>
        <filter id="lg"><feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <style>{`
          @keyframes dash-draw{from{stroke-dashoffset:800}to{stroke-dashoffset:0}}
          @keyframes dot-pop{0%,100%{r:3}50%{r:5}}
          .lc-line{stroke-dasharray:800;animation:dash-draw 2.5s ease-out forwards;}
          .lc-dot{animation:dot-pop 2s ease-in-out infinite;}
        `}</style>
      </defs>
      {[50,90,130,170].map(y=>(
        <line key={y} x1="20" y1={y} x2="300" y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="1"/>
      ))}
      <path d={area} fill="url(#la-grad)"/>
      <polyline className="lc-line" points={polyline} fill="none"
        stroke="#06b6d4" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" filter="url(#lg)"/>
      {pts.map(([x,y],i)=>(
        <circle key={i} className="lc-dot" cx={x} cy={y} r="3"
          fill="#06b6d4" stroke="rgba(6,182,212,0.4)" strokeWidth="4"
          style={{animationDelay:`${i*0.15}s`}}/>
      ))}
    </svg>
  );
}

function HeroSection({ onAnalyzeClick, onNavClick }) {
  const { user } = useAuth();
  return (
    <section id="home" className="relative min-h-screen flex flex-col items-center overflow-hidden bg-black">
      <div className="absolute inset-0 z-0"><PerspectiveGrid gridSize={20} fadeRadius={65}/></div>
      <div className="absolute inset-0 z-1 bg-radial-[ellipse_at_center] from-transparent via-black/40 to-black pointer-events-none"/>

      <div className="relative z-10 w-full flex items-center px-8 py-5">
        <div className="shrink-0 w-44">
          <span className="logo-brand text-2xl font-black tracking-tight cursor-pointer select-none"
            onClick={()=>onNavClick("/")}>AnalyzeAI</span>
        </div>
        <div className="flex-1 flex justify-center">
          <SpotlightNavbar items={NAV_ITEMS} className="pt-0"
            onItemClick={(item)=>onNavClick(item.href)}/>
        </div>
        {/* Auth-aware right side */}
        <div className="shrink-0 flex justify-end items-center gap-2 min-w-44">
          {user ? (
            <>
              <button onClick={() => onNavClick("/profile")}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/10 hover:border-violet-500/40 text-white/60 hover:text-white text-sm transition-all cursor-pointer">
                <div className="w-5 h-5 rounded-full bg-violet-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {user.name?.[0]?.toUpperCase()}
                </div>
                <span className="hidden sm:block">{user.name?.split(" ")[0]}</span>
              </button>
              <button onClick={onAnalyzeClick}
                className="px-5 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer shadow-[0_0_16px_rgba(139,92,246,0.45)] whitespace-nowrap">
                Analyze →
              </button>
            </>
          ) : (
            <>
              <button onClick={() => onNavClick("/login")}
                className="px-4 py-2 rounded-full border border-white/10 hover:border-white/30 text-white/50 hover:text-white text-sm transition-all cursor-pointer">
                Log In
              </button>
              <button onClick={() => onNavClick("/signup")}
                className="px-4 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer shadow-[0_0_12px_rgba(139,92,246,0.4)]">
                Sign Up
              </button>
            </>
          )}
        </div>
      </div>

      <div className="relative z-10 flex flex-col items-center justify-center flex-1 text-center px-6 pt-4 pb-24 gap-6">
        <span className="px-4 py-1.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300 text-xs font-semibold tracking-widest uppercase backdrop-blur-sm">
          LangGraph &middot; 6 Agents &middot; No Code Required
        </span>
        <MorphText
          words={["ANALYZE","VALIDATE","VISUALIZE","REPORT"]}
          subtext="Upload your CSV. Six agents do the rest — clean, analyze, visualize, and generate your report."
          fontSize="clamp(3rem, 11vw, 7.5rem)"
          textClassName="text-white"
          subtextClassName="text-white/50 text-base font-normal tracking-wide"
        />
        <div className="flex flex-wrap gap-4 justify-center mt-2">
          <AnimatedButton as="button" onClick={onAnalyzeClick} className="px-8 py-3 text-sm font-semibold cursor-pointer">
            Start Analyzing
          </AnimatedButton>
          <a href="#howitworks"
            className="px-8 py-3 text-sm font-semibold rounded-full border border-violet-500/30 text-violet-300 hover:text-violet-100 hover:border-violet-400/50 transition-colors duration-200">
            See How It Works
          </a>
        </div>
        <p className="text-white/20 text-xs tracking-widest mt-4">
          SALES DATA &middot; FINANCIAL RECORDS &middot; EXPENSE SHEETS &middot; TRANSACTION LOGS
        </p>
      </div>

      <style>{`
        .logo-brand {
          background: linear-gradient(90deg,#fff 0%,#c4b5fd 40%,#8b5cf6 60%,#fff 100%);
          background-size:200% auto;
          -webkit-background-clip:text; background-clip:text;
          -webkit-text-fill-color:transparent;
          filter:drop-shadow(0 0 8px rgba(139,92,246,0.5));
          transition:filter 0.3s ease;
        }
        .logo-brand:hover {
          animation:logo-wave 1.2s linear infinite;
          filter:drop-shadow(0 0 16px rgba(139,92,246,0.9));
        }
        @keyframes logo-wave { to { background-position:200% center; } }
      `}</style>
    </section>
  );
}

function StatsSection() {
  return (
    <section id="stats" className="relative bg-[#080808] py-24 px-6 border-t border-white/5">
      <div className="max-w-5xl mx-auto">
        <p className="text-center text-white/30 text-xs font-semibold tracking-widest uppercase mb-12">By the numbers</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-12">
          {STATS.map((stat)=>(
            <div key={stat.label} className="flex flex-col items-center gap-2">
              <div className="flex items-end gap-0.5">
                <AnimatedNumber value={stat.value} className="text-6xl font-black text-violet-300 tabular-nums"/>
                <span className="text-3xl font-bold text-white/40 mb-1">{stat.suffix}</span>
              </div>
              <p className="text-white/40 text-sm font-medium tracking-wide text-center">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  return (
    <section id="features" className="relative bg-black py-28 px-6 border-t border-white/5">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <p className="text-violet-400/60 text-xs font-semibold tracking-widest uppercase mb-3">What we do</p>
          <h2 className="text-4xl sm:text-5xl font-black text-white tracking-tight">Built for serious analysis.</h2>
          <p className="mt-4 text-white/40 text-lg max-w-xl mx-auto">
            Every stage of the analytics pipeline is owned by a dedicated agent — deterministic, validated, and auditable.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 justify-items-center">
          {[
            { title:"6-Agent Orchestration", preset:"aurora", viz:<NetworkGraph/>,
              desc:"A LangGraph DAG sequences six specialized agents: Structural Profiler → Semantic Tagger → Preprocessor → Statistics & Viz → Quality Guardrail → Report Generator." },
            { title:"Statistical Analysis", preset:"ocean", viz:<BarChart/>,
              desc:"Descriptive stats, correlation matrices, trend detection, growth rates, and time-series regression — all computed deterministically with NumPy, SciPy, and Statsmodels." },
            { title:"Professional Reports", preset:"sunset", viz:<LineChart/>,
              desc:"Auto-generated PDF/HTML reports with charts, plain-language narrative insights, and recommendations — produced in minutes, not days." },
          ].map((f)=>(
            <GlowBorderCard key={f.title} colorPreset={f.preset} width="100%" height="auto" aspectRatio="unset" className="bg-black">
              <div className="p-6 flex flex-col gap-4 h-full">
                <div className="rounded-xl bg-white/3 border border-white/5 p-3 overflow-hidden">{f.viz}</div>
                <h3 className="text-xl font-bold text-white">{f.title}</h3>
                <p className="text-white/50 text-sm leading-relaxed flex-1">{f.desc}</p>
              </div>
            </GlowBorderCard>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorksSection({ onAnalyzeClick }) {
  const steps = [
    { n:"01", title:"Upload CSV",      desc:"Drag and drop your sales, financial, or transaction CSV file. Supports files up to 100 MB." },
    { n:"02", title:"Agents Run",      desc:"Six agents process your data in sequence — profiling, cleaning, analyzing, visualizing, validating, and writing insights." },
    { n:"03", title:"Watch Live",      desc:"A real-time progress stream shows each agent status, output summaries, and validation warnings as they happen." },
    { n:"04", title:"Download Report", desc:"Receive a professionally formatted PDF or HTML report ready to share with stakeholders — no editing required." },
  ];
  return (
    <section id="howitworks" className="relative bg-[#080808] py-28 px-6 border-t border-white/5">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <p className="text-violet-400/60 text-xs font-semibold tracking-widest uppercase mb-3">How it works</p>
          <h2 className="text-4xl font-black text-white tracking-tight">Four steps. Full report.</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((s)=>(
            <div key={s.n} className="flex flex-col gap-3 p-6 rounded-2xl border border-white/5 bg-white/2 hover:border-violet-500/30 transition-colors duration-300">
              <span className="text-4xl font-black text-violet-500/40">{s.n}</span>
              <h3 className="text-white font-bold text-lg">{s.title}</h3>
              <p className="text-white/40 text-sm leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
        <div className="flex justify-center mt-12">
          <AnimatedButton as="button" onClick={onAnalyzeClick} className="px-10 py-3 text-sm font-semibold">
            Try It Now
          </AnimatedButton>
        </div>
      </div>
    </section>
  );
}

function FaqSection() {
  return (
    <section id="faq" className="relative bg-black py-28 px-6 border-t border-white/5">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-violet-400/60 text-xs font-semibold tracking-widest uppercase mb-3">Got questions?</p>
          <h2 className="text-4xl font-black text-white tracking-tight">Frequently asked.</h2>
        </div>
        <FaqAccordion items={FAQ_ITEMS} title=""/>
      </div>
    </section>
  );
}

function FooterSection() {
  return (
    <footer id="contact" className="bg-[#080808] border-t border-white/5 py-12 px-6">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <span className="logo-brand text-xl font-black tracking-tight select-none">AnalyzeAI</span>
        <p className="text-white/20 text-xs text-center">
          &copy; {new Date().getFullYear()} AnalyzeAI &middot; Thapathali Campus, IOE, TU &middot; Minor Project BCT 2080
        </p>
        <style>{`
          .logo-brand{background:linear-gradient(90deg,#fff 0%,#c4b5fd 40%,#8b5cf6 60%,#fff 100%);background-size:200% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;filter:drop-shadow(0 0 8px rgba(139,92,246,0.5));}
        `}</style>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const handleNavClick = (href) => {
    if (href.startsWith("/")) {
      navigate(href);
    } else {
      const el = document.querySelector(href);
      if (el) el.scrollIntoView({ behavior:"smooth" });
    }
  };
  return (
    <div className="dark min-h-screen bg-black font-sans antialiased">
      <HeroSection onAnalyzeClick={()=>navigate("/analyze")} onNavClick={handleNavClick}/>
      <StatsSection/>
      <FeaturesSection/>
      <HowItWorksSection onAnalyzeClick={()=>navigate("/analyze")}/>
      <FaqSection/>
      <FooterSection/>
    </div>
  );
}
