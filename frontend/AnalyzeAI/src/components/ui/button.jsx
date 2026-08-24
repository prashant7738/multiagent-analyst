import React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * The one button primitive (shadcn-style, cva variants). Variants map to
 * hierarchy, not decoration: primary (one per view), secondary, ghost, danger.
 *
 * Press feedback: scale(0.97) over 160ms ease-out — the interface "hears" you.
 */
const buttonVariants = cva(
  cn(
    "pressable inline-flex items-center justify-center rounded-(--radius-control) font-medium",
    "transition-colors duration-150 cursor-pointer select-none",
    "disabled:cursor-not-allowed disabled:pointer-events-none"
  ),
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-white hover:bg-accent-hover disabled:bg-raised disabled:text-ink-faint",
        secondary:
          "border border-line-strong text-ink hover:border-ink-muted disabled:text-ink-faint",
        ghost: "text-ink-secondary hover:text-ink hover:bg-raised",
        danger: "bg-danger text-white hover:opacity-90",
      },
      size: {
        sm: "h-8 px-3 text-xs gap-1.5",
        md: "h-10 px-4 text-sm gap-2",
        lg: "h-12 px-6 text-base gap-2",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export default function Button({
  variant = "primary",
  size = "md",
  as = "button",
  className,
  children,
  ...props
}) {
  const Tag = as;
  return (
    <Tag className={cn(buttonVariants({ variant, size }), className)} {...props}>
      {children}
    </Tag>
  );
}

export { buttonVariants };
