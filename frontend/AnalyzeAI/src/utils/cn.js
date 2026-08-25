import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge classnames with Tailwind CSS conflict resolution
 * Combines clsx for conditional classes with twMerge for Tailwind specificity
 * @param {...any} classes - Class names to merge
 * @returns {string} Merged class string
 */
export function cn(...classes) {
  return twMerge(clsx(classes));
}
