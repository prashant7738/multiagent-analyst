import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Download, FileText, Table, Code, X, Check, Loader, CheckCircle } from 'lucide-react';
import { reportDownloadUrl } from '@/lib/api';

/**
 * Report Download Component
 * Matches the AnalyzeAI theme: dark backgrounds, orange/amber accent colors, semantic typography
 */

const DownloadReportModal = ({ isOpen, onClose, reportData, jobId }) => {
  const [selectedFormat, setSelectedFormat] = useState('html');
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadComplete, setDownloadComplete] = useState(false);

  const downloadOptions = [
    {
      id: 'html',
      name: 'HTML Report',
      description: 'Interactive web format, perfect for sharing and viewing in any browser',
      icon: FileText,
      color: 'from-orange-500 to-amber-500',
      bgGradient: 'from-orange-500/10 to-amber-500/10',
      borderColor: 'border-orange-500/20 hover:border-orange-500/40',
    },
    {
      id: 'pdf',
      name: 'PDF Report',
      description: 'Professional PDF document, ideal for printing and archiving',
      icon: FileText,
      color: 'from-rose-500 to-pink-500',
      bgGradient: 'from-rose-500/10 to-pink-500/10',
      borderColor: 'border-rose-500/20 hover:border-rose-500/40',
    },
  ];

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      // Use jobId prop first, then fall back to job_id from report data
      const actualJobId = jobId || reportData?.job_id;

      if (!actualJobId) {
        throw new Error('Job ID is missing. Please reload the page and try again.');
      }

      // Call the backend API to get the report with selected format
      const reportUrl = reportDownloadUrl(actualJobId, selectedFormat);

      // Fetch the report file from the backend
      const response = await fetch(reportUrl);
      if (!response.ok) {
        throw new Error(`Failed to download ${selectedFormat.toUpperCase()} report: ${response.statusText}`);
      }

      // Get the file content
      const blob = await response.blob();

      // Use appropriate extension based on selected format
      const extension = selectedFormat === 'pdf' ? 'pdf' : 'html';

      // Create a download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `insight_report_${actualJobId?.slice(0, 8) || 'export'}.${extension}`;
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(link);

      setDownloadComplete(true);
      setTimeout(() => {
        setDownloadComplete(false);
        onClose();
      }, 2000);
    } catch (error) {
      console.error('Download failed:', error);
      console.error('JobID:', jobId);
      console.error('Report data:', reportData);
      alert(`Download error: ${error.message}\n\nJobID: ${jobId}`);
    } finally {
      setIsDownloading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-md p-4"
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.9, opacity: 0, y: 20 }}
        className="w-full max-w-2xl max-h-[90vh] rounded-sm shadow-2xl overflow-hidden bg-canvas border border-line flex flex-col"
      >
        {/* Header */}
        <div className="relative overflow-hidden border-b border-line p-8 bg-raised">
          <div className="absolute -right-20 -top-20 w-40 h-40 bg-gradient-to-br from-orange-500 to-amber-500 opacity-5 rounded-full blur-3xl" />
          <div className="relative flex items-center justify-between">
            <div>
              <h2 className="text-3xl font-bold text-white flex items-center gap-3">
                <div className="p-3 rounded-sm bg-gradient-to-br from-orange-500 to-amber-500">
                  <Download className="w-6 h-6 text-white" />
                </div>
                Download Report
              </h2>
              <p className="text-sm text-ink-secondary mt-2">
                Export your analysis in your preferred format for sharing and archiving
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={onClose}
              className="p-2 rounded-sm text-ink-secondary hover:bg-canvas hover:text-white transition-colors"
            >
              <X className="w-6 h-6" />
            </motion.button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          <p className="text-sm font-semibold text-ink-secondary mb-4 uppercase tracking-wide">
            Select Format
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
            {downloadOptions.map((option) => {
              const Icon = option.icon;
              const isSelected = selectedFormat === option.id;

              return (
                <motion.button
                  key={option.id}
                  whileHover={{ y: -4 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setSelectedFormat(option.id)}
                  className={`relative p-6 rounded-sm transition-all overflow-hidden group border ${
                    isSelected ? 'border-orange-500/60 bg-orange-500/10' : 'border-line bg-raised hover:border-orange-500/30'
                  }`}
                >
                  <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity" style={{
                    background: 'radial-gradient(circle at center, rgba(249, 115, 22, 0.05), transparent)',
                  }} />
                  <div className="relative z-10">
                    <div className={`inline-flex p-4 rounded-sm bg-gradient-to-br ${option.color} mb-4 group-hover:scale-110 transition-transform`}>
                      <Icon className="w-6 h-6 text-white" />
                    </div>
                    <h3 className="font-bold text-white text-base mb-2">
                      {option.name}
                    </h3>
                    <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                      {option.description}
                    </p>
                    {isSelected && (
                      <motion.div
                        initial={{ scale: 0, rotate: -180 }}
                        animate={{ scale: 1, rotate: 0 }}
                        className="flex items-center justify-center gap-2 pt-3 border-t border-orange-500/20"
                      >
                        <Check className="w-5 h-5 text-orange-500" />
                        <span className="text-xs font-semibold text-orange-500">Selected</span>
                      </motion.div>
                    )}
                  </div>
                </motion.button>
              );
            })}
          </div>

          {/* Features */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-sm p-5 mb-6 overflow-hidden group relative border border-orange-500/20 bg-orange-500/5"
          >
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity" style={{
              background: 'radial-gradient(circle at center, rgba(249, 115, 22, 0.05), transparent)',
            }} />
            <div className="relative z-10 space-y-2">
              <p className="text-sm font-bold text-orange-400 flex items-center gap-2">
                <CheckCircle className="w-5 h-5" />
                Report Includes
              </p>
              <div className="grid grid-cols-2 gap-2 text-xs text-ink-secondary">
                <div className="flex items-center gap-2">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" />
                  Executive Summary
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" />
                  Key Findings
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" />
                  Quality Metrics
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" />
                  Visualizations
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" />
                  Recommendations
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500" />
                  Full Details
                </div>
              </div>
            </div>
          </motion.div>

          {/* Download Progress */}
          {isDownloading && (
            <div className="mb-6">
              <div className="flex items-center justify-center gap-2 mb-3">
                <Loader className="w-5 h-5 text-orange-500 animate-spin" />
                <p className="text-sm font-medium text-white">
                  Preparing your {selectedFormat.toUpperCase()} report...
                </p>
              </div>
              <div className="w-full h-2 bg-neutral-800 rounded-full overflow-hidden">
                <motion.div
                  animate={{ width: '100%' }}
                  transition={{ duration: 1.5, ease: 'easeInOut' }}
                  className="h-full bg-gradient-to-r from-orange-500 to-amber-500"
                />
              </div>
            </div>
          )}

          {downloadComplete && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 p-4 bg-success-subtle border border-orange-500/30 rounded-sm flex items-center gap-3"
            >
              <Check className="w-5 h-5 text-orange-500" />
              <p className="text-sm font-medium text-white">
                Your report has been downloaded successfully!
              </p>
            </motion.div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-line p-6 flex gap-3 justify-end bg-raised flex-shrink-0">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={onClose}
            disabled={isDownloading}
            className="px-6 py-3 text-ink-secondary hover:bg-canvas hover:text-white rounded-sm transition-colors font-semibold disabled:opacity-50"
          >
            Cancel
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleDownload}
            disabled={isDownloading || downloadComplete}
            className="px-8 py-3 bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 disabled:from-neutral-600 disabled:to-neutral-700 text-white rounded-sm transition-all font-semibold flex items-center gap-2 shadow-lg hover:shadow-xl"
          >
            {isDownloading ? (
              <>
                <Loader className="w-4 h-4 animate-spin" />
                <span>Preparing {selectedFormat.toUpperCase()}...</span>
              </>
            ) : downloadComplete ? (
              <>
                <Check className="w-5 h-5" />
                <span>Downloaded!</span>
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                <span>Download {selectedFormat === 'html' ? 'HTML' : 'PDF'}</span>
              </>
            )}
          </motion.button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default DownloadReportModal;
