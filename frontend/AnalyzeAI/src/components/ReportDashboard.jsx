import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, AlertCircle, AlertTriangle, CheckCircle, BarChart3, Download } from 'lucide-react';
import { motion } from 'framer-motion';
import DownloadReportModal from './DownloadReportModal';

// Module scope, not inside ReportDashboard: a component defined inside another
// component's render body gets a new identity every render, so React remounts it
// and resets its state (here, `count`) on every parent re-render - the animation
// never got a chance to finish counting up before being reset back to 0.
const AnimatedCounter = ({ end, animate, suffix = '' }) => {
  const [count, setCount] = React.useState(0);
  React.useEffect(() => {
    if (!animate) return;
    let startTime;
    let frameId;
    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / 2000, 1);
      setCount(Math.floor(progress * end));
      if (progress < 1) frameId = requestAnimationFrame(step);
    };
    frameId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameId);
  }, [end, animate]);
  return `${count}${suffix}`;
};

const ReportDashboard = ({ reportData }) => {
  const [expandedSections, setExpandedSections] = useState({
    overview: true,
    findings: true,
    insights: true,
    analysis: true,
    recommendations: true,
    details: false,
  });

  const [animateNumbers, setAnimateNumbers] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);

  useEffect(() => {
    setAnimateNumbers(true);
  }, []);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const reportData_ = reportData || {};
  const summary = reportData_.summary || {};
  const data_quality = reportData_.data_quality || {};
  const validation = reportData_.validation || {};
  const insight_narrative = reportData_.insight_narrative || {};
  const { facts = {}, narrative = {}, kpis = [] } = reportData_;

  const facts_ = facts.data_quality ? facts : {
    data_quality: data_quality,
    validation: validation,
    dataset: {
      raw_rows: summary.rows,
      raw_cols: summary.columns,
    },
    top_correlations: [],
    significant_trends: [],
    data_quality_detail: data_quality,
  };

  const narrative_ = narrative.executive_summary ? narrative : {
    executive_summary: insight_narrative.executive_summary,
    key_findings: insight_narrative.key_findings || [],
    bottom_line: insight_narrative.bottom_line,
    plain_language_insights: insight_narrative.plain_language_insights || [],
    recommendations: insight_narrative.recommendations || [],
    risks_and_caveats: insight_narrative.risks_and_caveats || [],
  };

  const quality = data_quality.overall_quality_score || 0;
  const validationScore = validation.overall_validation_score || 0;
  const confidence = reportData_.reliability?.overall_confidence || 0.85;

  // "llm" (Groq/Gemini classified each column this run) or "fallback" (both providers
  // failed, so metadata-only heuristics were used instead) — see agent_2.py / result_builder.py.
  const taggingSource = summary.semantic_tagging_source;
  const taggingFellBack = taggingSource === "fallback";

  const SectionCard = ({ title, icon: Icon, children, sectionKey }) => (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="border border-line rounded-sm overflow-hidden bg-raised"
    >
      <button
        onClick={() => toggleSection(sectionKey)}
        className="w-full px-6 py-4 flex items-center justify-between hover:bg-raised transition-colors"
      >
        <div className="flex items-center gap-3">
          <Icon className="w-5 h-5 text-ink-secondary" />
          <h3 className="font-semibold text-ink text-base">{title}</h3>
        </div>
        <motion.div animate={{ rotate: expandedSections[sectionKey] ? 180 : 0 }} transition={{ duration: 0.2 }}>
          {expandedSections[sectionKey] ? (
            <ChevronUp className="w-5 h-5 text-ink-secondary" />
          ) : (
            <ChevronDown className="w-5 h-5 text-ink-secondary" />
          )}
        </motion.div>
      </button>
      {expandedSections[sectionKey] && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.2 }}
          className="px-6 py-5 border-t border-line"
        >
          {children}
        </motion.div>
      )}
    </motion.div>
  );

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="max-w-7xl mx-auto px-6 py-12">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-12"
        >
          <h1 className="text-3xl font-serif font-bold text-ink mb-2">
            Analysis Results
          </h1>
          <p className="text-sm text-ink-secondary">
            Comprehensive insights and metrics from your dataset
          </p>
        </motion.div>

        {/* Key Metrics */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12"
        >
          {/* Quality Score */}
          <motion.div
            className="border border-neutral-200 dark:border-neutral-800 rounded-sm p-6 bg-white dark:bg-neutral-900"
            whileHover={{ y: -2 }}
          >
            <p className="text-xs font-medium uppercase tracking-widest text-black dark:text-neutral-300 mb-3">Data Quality</p>
            <p className="text-5xl font-bold text-black dark:text-white font-mono mb-2">
              {animateNumbers ? <AnimatedCounter end={Math.round(quality)} animate={animateNumbers} /> : Math.round(quality)}
            </p>
            <p className="text-xs text-black dark:text-neutral-300 font-medium">
              {quality >= 80 ? 'Excellent' : quality >= 60 ? 'Good' : 'Fair'}
            </p>
          </motion.div>

          {/* Validation Score */}
          <motion.div
            className="border border-neutral-200 dark:border-neutral-800 rounded-sm p-6 bg-white dark:bg-neutral-900"
            whileHover={{ y: -2 }}
          >
            <p className="text-xs font-medium uppercase tracking-widest text-black dark:text-neutral-300 mb-3" style={{ color: 'black' }}>Validation</p>
            <p className="text-5xl font-bold text-black dark:text-white font-mono mb-2" style={{ color: 'black' }}>
              {animateNumbers ? <AnimatedCounter end={Math.round(validationScore)} animate={animateNumbers} /> : Math.round(validationScore)}
            </p>
            <p className="text-xs text-black dark:text-neutral-300 font-medium" style={{ color: 'black' }}>
              {validationScore >= 60 ? 'Verified' : 'Review Required'}
            </p>
          </motion.div>

          {/* Confidence */}
          <motion.div
            className="border border-neutral-200 dark:border-neutral-800 rounded-sm p-6 bg-white dark:bg-neutral-900"
            whileHover={{ y: -2 }}
          >
            <p className="text-xs font-medium uppercase tracking-widest text-black dark:text-neutral-300 mb-3" style={{ color: 'black' }}>Confidence</p>
            <p className="text-5xl font-bold text-black dark:text-white font-mono mb-2" style={{ color: 'black' }}>
              {animateNumbers ? <AnimatedCounter end={Math.round(confidence * 100)} animate={animateNumbers} suffix="%" /> : `${Math.round(confidence * 100)}%`}
            </p>
            <p className="text-xs text-black dark:text-neutral-300 font-medium" style={{ color: 'black' }}>Analysis Ready</p>
          </motion.div>
        </motion.div>

        {/* Content Sections */}
        <div className="space-y-6 mb-12">
          {/* Overview */}
          <SectionCard title="Dataset Overview" icon={BarChart3} sectionKey="overview">
            <div className="space-y-4">
              {taggingSource && (
                <div
                  className={`flex items-center gap-2 rounded-sm border p-3 text-xs font-medium ${
                    taggingFellBack
                      ? "border-warning/30 bg-warning-subtle text-warning"
                      : "border-success/30 bg-success/10 text-success"
                  }`}
                >
                  {taggingFellBack ? (
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                  ) : (
                    <CheckCircle className="h-4 w-4 shrink-0" />
                  )}
                  <span>
                    {taggingFellBack
                      ? `Column semantics used heuristic fallback — the AI model was unavailable during this run${
                          summary.semantic_tagging_error ? ` (${summary.semantic_tagging_error})` : ""
                        }.`
                      : "Column semantics were classified by the AI model (Groq or Gemini)."}
                  </span>
                </div>
              )}
              {narrative_.executive_summary && (
                <div className="border border-neutral-200 dark:border-neutral-800 p-4 rounded-sm bg-neutral-50 dark:bg-neutral-800">
                  <p className="font-semibold text-black dark:text-white mb-2 text-sm">Executive Summary</p>
                  <p className="text-black dark:text-neutral-200 text-sm leading-relaxed">{narrative_.executive_summary}</p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-4">
                {facts_.dataset?.raw_rows && (
                  <div className="border border-neutral-200 dark:border-neutral-800 p-4 rounded-sm bg-neutral-50 dark:bg-neutral-800">
                    <p className="text-xs font-semibold text-black dark:text-neutral-300 uppercase tracking-widest">Records</p>
                    <p className="text-3xl font-bold text-black dark:text-white mt-2">{facts_.dataset.raw_rows.toLocaleString()}</p>
                  </div>
                )}
                {facts_.dataset?.raw_cols && (
                  <div className="border border-neutral-200 dark:border-neutral-800 p-4 rounded-sm bg-neutral-50 dark:bg-neutral-800">
                    <p className="text-xs font-semibold text-black dark:text-neutral-300 uppercase tracking-widest">Columns</p>
                    <p className="text-3xl font-bold text-black dark:text-white mt-2">{facts_.dataset.raw_cols}</p>
                  </div>
                )}
              </div>
            </div>
          </SectionCard>

          {/* Key Findings */}
          {narrative_.key_findings && narrative_.key_findings.length > 0 && (
            <SectionCard title="Key Findings" icon={CheckCircle} sectionKey="findings">
              <div className="space-y-3">
                {narrative_.key_findings.map((finding, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="border border-neutral-200 dark:border-neutral-800 p-4 rounded-sm bg-neutral-50 dark:bg-neutral-800"
                  >
                    <div className="flex gap-3">
                      <div className="shrink-0">
                        <div className="flex items-center justify-center h-7 w-7 rounded-full bg-neutral-300 dark:bg-neutral-600 text-black dark:text-white">
                          <span className="font-bold text-xs">{idx + 1}</span>
                        </div>
                      </div>
                      <p className="text-black dark:text-neutral-200 text-sm leading-relaxed mt-1">{finding}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </SectionCard>
          )}

          {/* Insights */}
          {narrative_.plain_language_insights && narrative_.plain_language_insights.length > 0 && (
            <SectionCard title="Insights" icon={TrendingUp} sectionKey="insights">
              <div className="space-y-4">
                {narrative_.bottom_line && (
                  <div className="border-l-4 border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 p-4 rounded-sm">
                    <p className="font-semibold text-black dark:text-white text-sm mb-1">💡 Bottom Line</p>
                    <p className="text-black dark:text-neutral-200 text-sm leading-relaxed">{narrative_.bottom_line}</p>
                  </div>
                )}
                <div className="space-y-2">
                  {narrative_.plain_language_insights.map((insight, idx) => (
                    <motion.div key={idx} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="flex gap-3">
                      <div className="shrink-0 mt-1">
                        <div className="flex items-center justify-center h-5 w-5 rounded-full bg-neutral-200 dark:bg-neutral-700">
                          <span className="h-2 w-2 rounded-full bg-neutral-600 dark:bg-neutral-400" />
                        </div>
                      </div>
                      <p className="text-black dark:text-neutral-200 text-sm leading-relaxed">{insight}</p>
                    </motion.div>
                  ))}
                </div>
              </div>
            </SectionCard>
          )}

          {/* Recommendations */}
          {(narrative_.recommendations || narrative_.risks_and_caveats) && (
            <SectionCard title="Recommendations" icon={TrendingUp} sectionKey="recommendations">
              <div className="space-y-6">
                {narrative_.recommendations && narrative_.recommendations.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-black dark:text-white mb-3 text-sm">Recommended Actions</h4>
                    <div className="space-y-2">
                      {narrative_.recommendations.map((rec, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="border-l-4 border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 p-3 rounded-sm"
                        >
                          <p className="text-black dark:text-neutral-200 text-sm">{rec}</p>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
                {narrative_.risks_and_caveats && narrative_.risks_and_caveats.length > 0 && (
                  <div className="pt-6 border-t border-neutral-200 dark:border-neutral-800">
                    <h4 className="font-semibold text-black dark:text-white mb-3 text-sm">Important Considerations</h4>
                    <div className="space-y-2">
                      {narrative_.risks_and_caveats.map((risk, idx) => (
                        <motion.div key={idx} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="flex gap-3 p-3 border border-neutral-200 dark:border-neutral-800 rounded-sm bg-neutral-50 dark:bg-neutral-800">
                          <AlertCircle className="w-5 h-5 text-black dark:text-neutral-300 shrink-0 mt-0.5" />
                          <p className="text-sm text-black dark:text-neutral-200">{risk}</p>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </SectionCard>
          )}
        </div>

        {/* Download Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="border border-neutral-200 dark:border-neutral-800 rounded-sm p-8 bg-white dark:bg-neutral-900 text-center mb-12"
        >
          <h2 className="text-2xl font-serif font-bold text-black dark:text-white mb-3">Export Your Report</h2>
          <p className="text-black dark:text-neutral-300 max-w-2xl mx-auto mb-6 text-sm">
            Download your complete analysis with executive summary, findings, quality metrics, and recommendations.
          </p>
          <motion.button
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowDownloadModal(true)}
            className="px-6 py-2.5 bg-accent hover:bg-accent font-semibold rounded-sm transition-all flex items-center justify-center gap-2 mx-auto"
            style={{ color: 'white', WebkitTextFillColor: 'white !important' }}
          >
            <Download className="w-4 h-4" style={{ color: 'white' }} />
            Download Report
          </motion.button>
        </motion.div>

        {/* Footer */}
        <div className="text-center text-sm text-black dark:text-neutral-300 pt-8 border-t border-neutral-200 dark:border-neutral-800">
          <p className="font-medium">Powered by AI-driven analysis pipeline</p>
        </div>
      </div>

      {/* Download Modal */}
      <DownloadReportModal
        isOpen={showDownloadModal}
        onClose={() => setShowDownloadModal(false)}
        reportData={reportData_}
        jobId={reportData_?.job_id}
      />
    </div>
  );
};

export default ReportDashboard;
