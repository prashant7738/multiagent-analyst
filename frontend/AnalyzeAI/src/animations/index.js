/**
 * Animation Library
 * Framer Motion presets and utilities for consistent micro-interactions
 */

// ─────────────────────────────────────────────────────────────────────────────
// Transitions & Timing
// ─────────────────────────────────────────────────────────────────────────────

export const transitions = {
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

  ease: {
    in: {
      duration: 0.3,
      ease: [0.4, 0, 1, 1],
    },
    out: {
      duration: 0.3,
      ease: [0, 0, 0.2, 1],
    },
    inOut: {
      duration: 0.3,
      ease: [0.4, 0, 0.2, 1],
    },
    custom: {
      duration: 0.3,
      ease: [0.16, 1, 0.3, 1], // Premium easing
    },
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Entrance Animations
// ─────────────────────────────────────────────────────────────────────────────

export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: transitions.ease.custom,
};

export const slideInUp = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -24 },
  transition: transitions.ease.custom,
};

export const slideInDown = {
  initial: { opacity: 0, y: -24 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 24 },
  transition: transitions.ease.custom,
};

export const slideInLeft = {
  initial: { opacity: 0, x: -24 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -24 },
  transition: transitions.ease.custom,
};

export const slideInRight = {
  initial: { opacity: 0, x: 24 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 24 },
  transition: transitions.ease.custom,
};

export const scaleIn = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.95 },
  transition: transitions.ease.custom,
};

// ─────────────────────────────────────────────────────────────────────────────
// Stagger Animations (for lists and grids)
// ─────────────────────────────────────────────────────────────────────────────

export const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.15,
    },
  },
};

export const staggerChild = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: transitions.ease.custom,
};

export const staggerChildFast = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: {
    duration: 0.2,
    ease: [0.16, 1, 0.3, 1],
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Hover & Interactive Effects
// ─────────────────────────────────────────────────────────────────────────────

export const hoverLift = {
  whileHover: { y: -4 },
  whileTap: { scale: 0.98, y: -2 },
  transition: transitions.spring.default,
};

export const hoverLiftSmall = {
  whileHover: { y: -2 },
  whileTap: { scale: 0.98 },
  transition: transitions.spring.default,
};

export const hoverLiftLarge = {
  whileHover: { y: -8 },
  whileTap: { scale: 0.96 },
  transition: transitions.spring.default,
};

export const hoverGlow = {
  whileHover: {
    boxShadow: '0 0 20px rgba(79, 70, 229, 0.4)',
  },
  transition: transitions.spring.default,
};

export const hoverScale = {
  whileHover: { scale: 1.05 },
  whileTap: { scale: 0.95 },
  transition: transitions.spring.default,
};

export const hoverScaleSmall = {
  whileHover: { scale: 1.02 },
  whileTap: { scale: 0.98 },
  transition: transitions.spring.default,
};

// ─────────────────────────────────────────────────────────────────────────────
// Interactive States (Button press feedback)
// ─────────────────────────────────────────────────────────────────────────────

export const buttonTap = {
  whileTap: {
    y: -1,
    scale: 0.98,
  },
  transition: transitions.spring.snappy,
};

export const buttonHover = {
  whileHover: {
    y: -2,
    scale: 1.02,
  },
  transition: transitions.spring.default,
};

// ─────────────────────────────────────────────────────────────────────────────
// Loading States
// ─────────────────────────────────────────────────────────────────────────────

export const pulse = {
  animate: {
    opacity: [1, 0.6, 1],
  },
  transition: {
    duration: 2,
    repeat: Infinity,
    ease: 'easeInOut',
  },
};

export const shimmer = {
  animate: {
    backgroundPosition: ['200% center', '-200% center'],
  },
  transition: {
    duration: 3,
    repeat: Infinity,
    ease: 'linear',
  },
};

export const spin = {
  animate: {
    rotate: 360,
  },
  transition: {
    duration: 1,
    repeat: Infinity,
    ease: 'linear',
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Error & Success States
// ─────────────────────────────────────────────────────────────────────────────

export const shake = {
  animate: {
    x: [-8, 8, -8, 8, 0],
  },
  transition: {
    duration: 0.4,
    ease: 'easeInOut',
  },
};

export const successCheckmark = {
  initial: { scale: 0, rotate: -180 },
  animate: { scale: 1, rotate: 0 },
  transition: transitions.spring.snappy,
};

// ─────────────────────────────────────────────────────────────────────────────
// Scroll-Reveal Animations
// ─────────────────────────────────────────────────────────────────────────────

export const viewportReveal = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.3 },
  transition: transitions.ease.custom,
};

export const viewportRevealStagger = (index) => ({
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.3 },
  transition: {
    ...transitions.ease.custom,
    delay: index * 0.1,
  },
});

// ─────────────────────────────────────────────────────────────────────────────
// Modal & Overlay Animations
// ─────────────────────────────────────────────────────────────────────────────

export const modalBackdrop = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.2 },
};

export const modalContent = {
  initial: { opacity: 0, scale: 0.9, y: 20 },
  animate: { opacity: 1, scale: 1, y: 0 },
  exit: { opacity: 0, scale: 0.9, y: 20 },
  transition: transitions.spring.default,
};

// ─────────────────────────────────────────────────────────────────────────────
// Dropdown & Expand Animations
// ─────────────────────────────────────────────────────────────────────────────

export const dropdownOpen = {
  initial: { opacity: 0, y: -10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
  transition: transitions.ease.custom,
};

export const expandCollapse = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1 },
  exit: { height: 0, opacity: 0 },
  transition: {
    ...transitions.ease.custom,
    height: {
      duration: 0.4,
    },
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Utility Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create staggered animation with custom delay
 * @param {number} index - Item index in list
 * @param {number} baseDelay - Base delay in seconds
 * @param {number} staggerDelay - Delay multiplier per item
 * @returns {object} Delay object for Framer Motion
 */
export const getStaggerDelay = (index, baseDelay = 0.1, staggerDelay = 0.1) => ({
  delay: baseDelay + index * staggerDelay,
});

/**
 * Combine animation variants with custom transition
 * @param {object} variant - Animation variant object
 * @param {object} customTransition - Custom transition override
 * @returns {object} Combined animation object
 */
export const withTransition = (variant, customTransition) => ({
  ...variant,
  transition: { ...variant.transition, ...customTransition },
});

/**
 * Create responsive animation
 * @param {object} mobileVariant - Mobile animation
 * @param {object} desktopVariant - Desktop animation
 * @param {number} breakpoint - Breakpoint in pixels (default: 768)
 * @returns {object} Responsive animation object
 */
export const responsiveAnimation = (mobileVariant, desktopVariant, breakpoint = 768) => {
  const isMobile = typeof window !== 'undefined' && window.innerWidth < breakpoint;
  return isMobile ? mobileVariant : desktopVariant;
};

/**
 * Get spring transition based on motion intensity
 * @param {number} intensity - Motion intensity (1-10)
 * @returns {object} Appropriate spring transition
 */
export const getSpringByIntensity = (intensity) => {
  if (intensity <= 3) return transitions.spring.gentle;
  if (intensity <= 6) return transitions.spring.default;
  if (intensity <= 8) return transitions.spring.snappy;
  return transitions.spring.bouncy;
};

export default {
  transitions,
  fadeIn,
  slideInUp,
  slideInDown,
  slideInLeft,
  slideInRight,
  scaleIn,
  staggerContainer,
  staggerChild,
  hoverLift,
  hoverScale,
  pulse,
  shake,
  successCheckmark,
  viewportReveal,
  modalContent,
  expandCollapse,
};
