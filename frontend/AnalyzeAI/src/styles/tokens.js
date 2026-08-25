/**
 * Global Design Tokens
 * Comprehensive design system for MultiAgent Analyst
 * Used across all components and pages for consistent, premium aesthetic
 */

export const colors = {
  // Neutral Base (Zinc)
  neutral: {
    50: '#fafafa',
    100: '#f4f4f5',
    200: '#e4e4e7',
    300: '#d4d4d8',
    400: '#a1a1a6',
    500: '#71717a',
    600: '#52525b',
    700: '#3f3f46',
    800: '#27272a',
    900: '#18181b',
    950: '#09090b',
  },

  // Primary Accent (Indigo)
  primary: {
    50: '#eef2ff',
    100: '#e0e7ff',
    200: '#c7d2fe',
    300: '#a5b4fc',
    400: '#818cf8',
    500: '#6366f1',
    600: '#4f46e5',
    700: '#4338ca',
    800: '#3730a3',
    900: '#312e81',
  },

  // Secondary Accent (Purple)
  secondary: {
    50: '#faf5ff',
    100: '#f3e8ff',
    200: '#e9d5ff',
    300: '#d8b4fe',
    400: '#c084fc',
    500: '#a855f7',
    600: '#9333ea',
    700: '#7e22ce',
    800: '#6b21a8',
    900: '#581c87',
  },

  // Status Colors
  success: '#10b981', // Emerald
  warning: '#f59e0b', // Amber
  error: '#ef4444',   // Red
  info: '#3b82f6',    // Blue

  // Glass Effect (for backgrounds)
  glass: {
    light: 'rgba(255, 255, 255, 0.3)',
    lighter: 'rgba(255, 255, 255, 0.1)',
    dark: 'rgba(31, 41, 55, 0.3)',
    darker: 'rgba(17, 24, 39, 0.3)',
  },
};

export const typography = {
  // Font Families
  fonts: {
    display: '"Space Grotesk", system-ui, -apple-system, sans-serif',
    body: '"DM Sans", system-ui, -apple-system, sans-serif',
    mono: '"Fira Code", "Courier New", monospace',
  },

  // Font Sizes (Tailwind scale)
  sizes: {
    xs: '12px',
    sm: '14px',
    base: '16px',
    lg: '18px',
    xl: '20px',
    '2xl': '24px',
    '3xl': '30px',
    '4xl': '36px',
    '5xl': '48px',
    '6xl': '60px',
    '7xl': '72px',
    '8xl': '96px',
  },

  // Font Weights
  weights: {
    thin: 100,
    extralight: 200,
    light: 300,
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    extrabold: 800,
    black: 900,
  },

  // Line Heights
  lineHeights: {
    none: 1,
    tight: 1.25,
    snug: 1.375,
    normal: 1.5,
    relaxed: 1.625,
    loose: 2,
  },

  // Letter Spacing
  tracking: {
    tighter: '-0.05em',
    tight: '-0.025em',
    normal: '0em',
    wide: '0.025em',
    wider: '0.05em',
    widest: '0.1em',
  },
};

export const spacing = {
  // Spacing scale (4px base)
  0: '0px',
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '20px',
  6: '24px',
  8: '32px',
  10: '40px',
  12: '48px',
  14: '56px',
  16: '64px',
  20: '80px',
  24: '96px',
  28: '112px',
  32: '128px',
  36: '144px',
  40: '160px',
  44: '176px',
  48: '192px',
  52: '208px',
  56: '224px',
  60: '240px',
  64: '256px',
  72: '288px',
  80: '320px',
  96: '384px',
};

export const blur = {
  none: '0px',
  sm: '8px',
  base: '12px',
  md: '16px',
  lg: '20px',
  xl: '24px',
  '2xl': '32px',
};

export const shadows = {
  none: 'none',
  sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
  base: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
  md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  xl: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
  '2xl': '0 25px 50px -12px rgb(0 0 0 / 0.25)',

  // Glass-specific shadows
  glass: 'inset 0 1px 0 rgba(255, 255, 255, 0.2)',
  glassLarge: '0 8px 32px rgba(0, 0, 0, 0.1)',
};

export const borderRadius = {
  none: '0px',
  sm: '4px',
  base: '8px',
  md: '12px',
  lg: '16px',
  xl: '20px',
  '2xl': '24px',
  '3xl': '32px',
  full: '9999px',
};

export const transitions = {
  // Motion Timing Functions
  ease: {
    in: 'cubic-bezier(0.4, 0, 1, 1)',
    out: 'cubic-bezier(0, 0, 0.2, 1)',
    inOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    custom: 'cubic-bezier(0.16, 1, 0.3, 1)', // Premium easing
  },

  // Duration (ms)
  duration: {
    fastest: 100,
    fast: 200,
    base: 300,
    normal: 400,
    slow: 500,
    slower: 600,
    slowest: 1000,
  },

  // Spring Physics (for Framer Motion)
  spring: {
    gentle: {
      type: 'spring',
      stiffness: 100,
      damping: 20,
      mass: 1,
    },
    default: {
      type: 'spring',
      stiffness: 300,
      damping: 30,
      mass: 1,
    },
    snappy: {
      type: 'spring',
      stiffness: 500,
      damping: 35,
      mass: 1,
    },
    bouncy: {
      type: 'spring',
      stiffness: 300,
      damping: 10,
      mass: 1,
    },
  },
};

// Animation Presets for Framer Motion
export const animationPresets = {
  // Fade Variants
  fadeIn: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
  },

  // Slide Variants
  slideInUp: {
    initial: { opacity: 0, y: 24 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -24 },
  },

  slideInDown: {
    initial: { opacity: 0, y: -24 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: 24 },
  },

  slideInLeft: {
    initial: { opacity: 0, x: -24 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: -24 },
  },

  slideInRight: {
    initial: { opacity: 0, x: 24 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: 24 },
  },

  // Scale Variants
  scaleIn: {
    initial: { opacity: 0, scale: 0.95 },
    animate: { opacity: 1, scale: 1 },
    exit: { opacity: 0, scale: 0.95 },
  },

  // Stagger Container (parent)
  staggerContainer: {
    animate: {
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  },

  // Stagger Child
  staggerChild: {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.4 },
  },
};

// Hover Effects
export const hoverEffects = {
  lift: { y: -4 },
  liftSmall: { y: -2 },
  liftLarge: { y: -8 },
  glow: { boxShadow: '0 0 20px rgba(79, 70, 229, 0.4)' },
  scale: { scale: 1.05 },
  scaleSmall: { scale: 1.02 },
  scaleLarge: { scale: 1.1 },
};

// Focus States (Accessibility)
export const focusStyles = {
  ring: 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary-500',
  ringDark: 'dark:focus-visible:ring-primary-400 dark:focus-visible:ring-offset-neutral-950',
};

// Responsive Breakpoints
export const breakpoints = {
  xs: 0,
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
};

// Z-Index Scale
export const zIndex = {
  hide: -1,
  auto: 'auto',
  0: 0,
  10: 10,
  20: 20,
  30: 30,
  40: 40,
  50: 50,
  dropdown: 1000,
  sticky: 1020,
  fixed: 1030,
  backdrop: 1040,
  offcanvas: 1050,
  modal: 1060,
  tooltip: 1070,
};

export default {
  colors,
  typography,
  spacing,
  blur,
  shadows,
  borderRadius,
  transitions,
  animationPresets,
  hoverEffects,
  focusStyles,
  breakpoints,
  zIndex,
};
