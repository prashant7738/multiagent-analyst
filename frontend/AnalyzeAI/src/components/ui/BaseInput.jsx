import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/utils/cn';

/**
 * BaseInput - Enhanced input component with floating labels and error states
 * Supports icons, error messages, and smooth focus transitions
 */
const BaseInput = React.forwardRef(
  (
    {
      label,
      error,
      icon: Icon,
      type = 'text',
      placeholder,
      size = 'md',
      fullWidth = false,
      className,
      containerClassName,
      disabled = false,
      ...props
    },
    ref,
  ) => {
    const [isFocused, setIsFocused] = useState(false);
    const [hasValue, setHasValue] = useState(false);

    const handleFocus = (e) => {
      setIsFocused(true);
      props.onFocus?.(e);
    };

    const handleBlur = (e) => {
      setIsFocused(false);
      setHasValue(e.target.value.length > 0);
      props.onBlur?.(e);
    };

    const handleChange = (e) => {
      setHasValue(e.target.value.length > 0);
      props.onChange?.(e);
    };

    const sizeStyles = {
      sm: 'px-3 py-2 text-sm',
      md: 'px-4 py-2.5 text-base',
      lg: 'px-4 py-3 text-base',
    };

    const baseStyles = cn(
      'w-full font-sans rounded-lg',
      'bg-neutral-100 dark:bg-neutral-900',
      'border-2 border-neutral-200 dark:border-neutral-800',
      'text-neutral-900 dark:text-neutral-100',
      'placeholder-neutral-400 dark:placeholder-neutral-600',
      'transition-all duration-200',
      'focus:outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:bg-white dark:focus:bg-neutral-950',
      disabled && 'opacity-50 cursor-not-allowed',
      error && 'border-error focus:border-error focus:ring-error/20',
      Icon && 'pl-10',
      sizeStyles[size],
      className,
    );

    const labelStyles = cn(
      'absolute left-4 transition-all duration-200 pointer-events-none',
      'text-neutral-600 dark:text-neutral-400',
      isFocused || hasValue ? [
        'text-xs -translate-y-2 bg-white dark:bg-neutral-950 px-1',
        'text-primary-600 dark:text-primary-400',
      ] : [
        'text-base translate-y-2',
      ],
    );

    return (
      <div className={cn('relative', fullWidth && 'w-full', containerClassName)}>
        {/* Input Wrapper */}
        <div className="relative">
          {/* Icon */}
          {Icon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400 dark:text-neutral-600 pointer-events-none">
              <Icon className={sizeStyles[size].includes('sm') ? 'h-4 w-4' : 'h-5 w-5'} />
            </div>
          )}

          {/* Input */}
          <input
            ref={ref}
            type={type}
            className={baseStyles}
            placeholder={placeholder}
            disabled={disabled}
            onFocus={handleFocus}
            onBlur={handleBlur}
            onChange={handleChange}
            {...props}
          />

          {/* Floating Label */}
          {label && (
            <label className={labelStyles}>
              {label}
              {props.required && <span className="text-error ml-1">*</span>}
            </label>
          )}
        </div>

        {/* Error Message */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="mt-2 text-sm text-error flex items-center gap-1"
            >
              <svg
                className="h-4 w-4 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M18.101 12.93a.75.75 0 00-1.025-1.09L10 16.864l-6.576-7.043a.75.75 0 10-1.025 1.09L10 18.914l8.101-5.984z"
                  clipRule="evenodd"
                />
              </svg>
              {error}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  },
);

BaseInput.displayName = 'BaseInput';

export default BaseInput;
