import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/utils/cn';

/**
 * BaseCard - Glassmorphic card component with optional backdrop blur
 * Supports gradient backgrounds, hover effects, and responsive padding
 */
const BaseCard = React.forwardRef(
  (
    {
      children,
      className,
      interactive = false,
      gradient = false,
      glassy = true,
      padding = 'md',
      rounded = 'lg',
      shadow = 'base',
      hover = 'lift',
      ...props
    },
    ref,
  ) => {
    const paddingStyles = {
      sm: 'p-3',
      md: 'p-6',
      lg: 'p-8',
      xl: 'p-10',
      none: 'p-0',
    };

    const roundedStyles = {
      sm: 'rounded-md',
      md: 'rounded-lg',
      lg: 'rounded-xl',
      xl: 'rounded-2xl',
      full: 'rounded-full',
    };

    const shadowStyles = {
      none: 'shadow-none',
      sm: 'shadow-sm',
      base: 'shadow-base',
      md: 'shadow-md',
      lg: 'shadow-lg',
      xl: 'shadow-xl',
    };

    const baseStyles = cn(
      'relative overflow-hidden transition-all',
      paddingStyles[padding],
      roundedStyles[rounded],
      shadowStyles[shadow],
      glassy && [
        'bg-white/30 dark:bg-white/5',
        'backdrop-blur-lg',
        'border border-white/30 dark:border-white/10',
      ],
      !glassy && [
        'bg-neutral-100 dark:bg-neutral-900',
        'border border-neutral-200 dark:border-neutral-800',
      ],
    );

    const hoverStyles = {
      lift: interactive && [
        'hover:shadow-lg hover:shadow-lg',
        'hover:translate-y-[-4px]',
      ],
      scale: interactive && [
        'hover:scale-105',
        'hover:shadow-lg',
      ],
      glow: interactive && [
        'hover:shadow-[0_0_20px_rgba(79,70,229,0.4)]',
        'dark:hover:shadow-[0_0_20px_rgba(79,70,229,0.3)]',
      ],
      none: [],
    };

    const gradientStyles = gradient && [
      'bg-gradient-to-br',
      'from-primary-50/50 dark:from-primary-950/10',
      'to-secondary-50/50 dark:to-secondary-950/10',
    ];

    const MotionComponent = interactive ? motion.div : 'div';

    const motionProps = interactive
      ? {
          whileHover: hover !== 'none' ? { y: hover === 'lift' ? -4 : 0 } : undefined,
          transition: { type: 'spring', stiffness: 300, damping: 30 },
        }
      : {};

    return (
      <MotionComponent
        ref={ref}
        className={cn(
          baseStyles,
          hoverStyles[hover] || [],
          gradientStyles,
          className,
        )}
        {...motionProps}
        {...props}
      >
        {/* Inner highlight for glassmorphic effect */}
        {glassy && (
          <div className="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent pointer-events-none rounded-inherit opacity-0 hover:opacity-100 transition-opacity" />
        )}

        {/* Content */}
        <div className="relative z-10">
          {children}
        </div>
      </MotionComponent>
    );
  },
);

BaseCard.displayName = 'BaseCard';

export default BaseCard;
