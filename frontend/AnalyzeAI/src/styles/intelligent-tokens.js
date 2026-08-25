/**
 * Intelligent Premium Design System
 * Serious, crafted, technical aesthetic
 * No SaaS hype. Pure data intelligence.
 */

export const intelligentTokens = {
  colors: {
    // Sophisticated neutral palette - warm grays
    background: {
      primary: '#FAFAF8',      // Off-white with warmth
      secondary: '#F3F1ED',    // Warm cream
      tertiary: '#E8E5DF',     // Warm taupe
      dark: '#0F0E0C',         // Deep charcoal
      darkSecondary: '#1A1916', // Warm dark gray
      darkTertiary: '#24221D',  // Darker warm gray
    },

    // Single warm accent - burnt sienna/rust
    accent: {
      primary: '#A0522D',      // Burnt sienna (warm, serious)
      light: '#C17A5C',        // Lighter rust
      dark: '#6B3420',         // Darker rust
    },

    // Technical data colors (minimal palette)
    data: {
      positive: '#2D5F4F',     // Deep teal (calm, confident)
      negative: '#8B4513',     // Saddle brown (serious warning)
      neutral: '#5C5550',      // Warm gray
      accent: '#A0522D',       // Burnt sienna for emphasis
    },

    // Text hierarchy
    text: {
      primary: '#0F0E0C',      // Deep charcoal
      secondary: '#3D3A35',    // Medium gray
      tertiary: '#6B6560',     // Light gray
      inverse: '#F5F3F0',      // Off-white
    },

    // Dark mode
    darkText: {
      primary: '#F5F3F0',      // Off-white
      secondary: '#D4D0C8',    // Light gray
      tertiary: '#A6A098',     // Dimmer gray
      inverse: '#0F0E0C',      // Deep charcoal
    },

    // Technical marginalia
    marginalia: '#A0522D',     // Burnt sienna for coordinates, IDs, etc
  },

  typography: {
    // Premium typefaces
    fontFamily: {
      display: '"Saol", "Tiempos Text", serif', // Editorial serif for headlines
      body: '"Söhne", "Inter", system-ui, sans-serif', // Modern sans for body
      mono: '"IBM Plex Mono", "Courier New", monospace', // Technical mono
    },

    sizes: {
      display: '4rem',         // 64px - monumental
      heading1: '2.5rem',      // 40px
      heading2: '1.875rem',    // 30px
      heading3: '1.5rem',      // 24px
      body: '1rem',            // 16px
      small: '0.875rem',       // 14px
      tiny: '0.75rem',         // 12px - marginalia
      micro: '0.625rem',       // 10px - extreme small
    },

    weights: {
      thin: 100,
      light: 300,
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
      extrabold: 800,
    },

    lineHeight: {
      tight: 1.1,
      normal: 1.5,
      relaxed: 1.75,
      loose: 2,
    },

    letterSpacing: {
      tight: '-0.02em',
      normal: '0em',
      wide: '0.05em',
      wider: '0.1em',
      technical: '0.02em', // For marginalia
    },
  },

  spacing: {
    xs: '0.5rem',    // 8px
    sm: '1rem',      // 16px
    md: '1.5rem',    // 24px
    lg: '2rem',      // 32px
    xl: '3rem',      // 48px
    '2xl': '4rem',   // 64px
    '3xl': '6rem',   // 96px
  },

  borderRadius: {
    none: '0',
    xs: '2px',       // Minimal, technical
    sm: '4px',
    md: '6px',
    lg: '8px',
    full: '9999px',
  },

  shadows: {
    none: 'none',
    xs: '0 1px 2px rgba(15, 14, 12, 0.05)',
    sm: '0 2px 4px rgba(15, 14, 12, 0.08)',
    md: '0 4px 8px rgba(15, 14, 12, 0.12)',
    lg: '0 8px 16px rgba(15, 14, 12, 0.15)',
    xl: '0 16px 32px rgba(15, 14, 12, 0.2)',
  },

  transitions: {
    fast: '150ms cubic-bezier(0.16, 1, 0.3, 1)',
    normal: '250ms cubic-bezier(0.16, 1, 0.3, 1)',
    slow: '350ms cubic-bezier(0.16, 1, 0.3, 1)',
  },

  // Technical marginalia elements
  marginalia: {
    fontSize: '0.625rem',      // 10px
    fontFamily: '"IBM Plex Mono"',
    color: '#A0522D',          // Burnt sienna
    opacity: 0.6,
    letterSpacing: '0.02em',
  },
};

export default intelligentTokens;
