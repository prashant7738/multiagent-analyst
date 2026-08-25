import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/utils/cn';
import { transitions } from '@/animations';

/**
 * BaseButton - Core button component with multiple variants and sizes
 * Supports loading, disabled, and icon states with smooth micro-interactions
 */
const BaseButton = React.forwardRef(
  (
    {
      children,
      variant = 'primary',
      size = 'md',
      icon: Icon,
      iconPosition = 'left',
      isLoading = false,
      disabled = false,
      fullWidth = false,
      className,
      ...props
    },
    ref,
  ) => {
    const baseStyles = 'relative inline-flex items-center justify-center font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed';

    const variantStyles = {
      primary:
        'bg-gradient-to-r from-primary-600 to-secondary-600 text-white hover:from-primary-700 hover:to-secondary-700 active:scale-95 shadow-lg hover:shadow-xl',
      secondary:
        'bg-neutral-200 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 hover:bg-neutral-300 dark:hover:bg-neutral-700 active:scale-95',
      ghost:
        'text-neutral-900 dark:text-neutral-100 hover:bg-neutral-100 dark:hover:bg-neutral-900 active:scale-95',
      danger:
        'bg-error text-white hover:bg-red-700 active:scale-95 shadow-lg hover:shadow-xl',
      success:
        'bg-success text-white hover:bg-emerald-600 active:scale-95 shadow-lg hover:shadow-xl',
    };

    const sizeStyles = {
      sm: 'px-3 py-1.5 text-sm rounded-lg gap-1',
      md: 'px-4 py-2.5 text-base rounded-lg gap-2',
      lg: 'px-6 py-3 text-lg rounded-xl gap-3',
      xl: 'px-8 py-4 text-lg rounded-xl gap-3',
      icon: 'p-2 rounded-lg',
      'icon-md': 'p-2.5 rounded-lg',
      'icon-lg': 'p-3 rounded-xl',
    };

    const content = (
      <>
        {isLoading ? (
          <svg
            className="animate-spin h-5 w-5"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : Icon && iconPosition === 'left' ? (
          <Icon className="h-5 w-5" />
        ) : null}

        {!isLoading && children && <span>{children}</span>}

        {Icon && iconPosition === 'right' && !isLoading ? <Icon className="h-5 w-5" /> : null}
      </>
    );

    return (
      <motion.button
        ref={ref}
        className={cn(
          baseStyles,
          variantStyles[variant],
          sizeStyles[size],
          fullWidth && 'w-full',
          className,
        )}
        disabled={disabled || isLoading}
        whileHover={!disabled && !isLoading ? { y: -2 } : undefined}
        whileTap={!disabled && !isLoading ? { scale: 0.98, y: 0 } : undefined}
        transition={transitions.spring.default}
        {...props}
      >
        {content}
      </motion.button>
    );
  },
);

BaseButton.displayName = 'BaseButton';

export default BaseButton;
