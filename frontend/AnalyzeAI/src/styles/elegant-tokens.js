/**
 * Elegant Modern Design System
 * Premium, sophisticated, high-quality aesthetic
 */

export const elegantTokens = {
  colors: {
    // Sophisticated neutral palette
    background: {
      primary: '#FAFBFC',
      secondary: '#F0F3F6',
      tertiary: '#E8EAED',
    },
    dark: {
      primary: '#0F1419',
      secondary: '#161B22',
      tertiary: '#21262D',
    },
    // Elegant accent colors
    accent: {
      primary: '#2563EB',      // Premium blue
      secondary: '#7C3AED',    // Elegant purple
      tertiary: '#06B6D4',     // Sophisticated cyan
    },
    // Status colors (elegant versions)
    status: {
      success: '#059669',
      warning: '#D97706',
      error: '#DC2626',
      info: '#0891B2',
    },
    // Text colors
    text: {
      primary: '#1F2937',
      secondary: '#6B7280',
      tertiary: '#9CA3AF',
      inverse: '#FFFFFF',
    },
    darkText: {
      primary: '#F9FAFB',
      secondary: '#E5E7EB',
      tertiary: '#D1D5DB',
      inverse: '#000000',
    },
  },

  typography: {
    fontFamily: {
      display: '"Inter", system-ui, -apple-system, sans-serif',
      body: '"Inter", system-ui, -apple-system, sans-serif',
      code: '"Fira Code", monospace',
    },
    sizes: {
      display: '3.5rem',  // 56px
      heading1: '2.5rem', // 40px
      heading2: '1.875rem', // 30px
      heading3: '1.5rem',  // 24px
      body: '1rem',        // 16px
      small: '0.875rem',   // 14px
      tiny: '0.75rem',     // 12px
    },
    weights: {
      thin: 100,
      extralight: 200,
      light: 300,
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
      extrabold: 800,
    },
    lineHeight: {
      tight: 1.2,
      normal: 1.5,
      relaxed: 1.75,
      loose: 2,
    },
  },

  spacing: {
    xs: '0.5rem',    // 8px
    sm: '1rem',      // 16px
    md: '1.5rem',    // 24px
    lg: '2rem',      // 32px
    xl: '2.5rem',    // 40px
    '2xl': '3rem',   // 48px
    '3xl': '4rem',   // 64px
  },

  borderRadius: {
    none: '0',
    sm: '0.375rem',   // 6px
    md: '0.5rem',     // 8px
    lg: '0.75rem',    // 12px
    xl: '1rem',       // 16px
    full: '9999px',
  },

  shadows: {
    none: 'none',
    xs: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    sm: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
  },

  transitions: {
    fast: '150ms ease-in-out',
    normal: '250ms ease-in-out',
    slow: '350ms ease-in-out',
  },
};

export default elegantTokens;
