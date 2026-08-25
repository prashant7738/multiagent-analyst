# Design System - MultiAgent Analyst

## Phase 1: Complete ✅

### What's Been Built

**Design Foundation**
- 🎨 **Design Tokens** (`src/styles/tokens.js`) - Complete token system with colors, typography, spacing, animations, shadows, blur effects
- 🎯 **Global Styles** (`src/styles/globals.css`) - Enhanced CSS variables, glassmorphic patterns, utilities, dark mode support
- ✨ **Animation Library** (`src/animations/index.js`) - 25+ Framer Motion presets for entrance, hover, loading, scroll states

**Base Components**
- `BaseButton` - 5 variants (primary, secondary, ghost, danger, success), 5 sizes, loading states, icon support
- `BaseCard` - Glassmorphic container with hover effects, gradients, shadow options, responsive padding
- `BaseInput` - Form input with floating labels, error states, icon support, focus animations

**Infrastructure**
- ✅ Path aliases configured (`@/components`, `@/utils`, `@/animations`)
- ✅ Tailwind CSS v4 with custom theme
- ✅ Dark mode via CSS variables
- ✅ Reduced motion support via `prefers-reduced-motion`
- ✅ Utility function `cn()` for class merging with Tailwind resolution

---

## Quick Start

### Using Design Tokens

```jsx
import { colors, spacing, transitions } from '@/styles/tokens';

// In components
<div style={{ color: colors.primary[600] }}>Hello</div>
<button style={{ padding: spacing[4] }}>Click me</button>
```

### Using Base Components

```jsx
import { BaseButton, BaseCard, BaseInput } from '@/components/ui';

// Button
<BaseButton variant="primary" size="md">
  Click me
</BaseButton>

// Card
<BaseCard glassy interactive>
  <h3>My Card</h3>
  <p>Glassmorphic content</p>
</BaseCard>

// Input
<BaseInput
  label="Email"
  type="email"
  placeholder="Enter your email"
  error={emailError}
/>
```

### Using Animations

```jsx
import { motion } from 'framer-motion';
import { slideInUp, hoverLift, staggerContainer } from '@/animations';

// Entrance animation
<motion.div {...slideInUp}>
  Slides up and fades in
</motion.div>

// Hover effect
<motion.button {...hoverLift}>
  Lifts on hover
</motion.button>

// Staggered list
<motion.div {...staggerContainer}>
  {items.map((item) => (
    <motion.div key={item.id} {...staggerChild}>
      {item.name}
    </motion.div>
  ))}
</motion.div>
```

---

## Design Tokens Reference

### Colors

**Primary Palette**
- `colors.primary` - Indigo (600 is main)
- `colors.secondary` - Purple (600 is main)
- `colors.neutral` - Zinc (base grays)
- `colors.success`, `colors.warning`, `colors.error` - Status

**Glass Effects**
- `colors.glass.light` - Light mode blur background
- `colors.glass.dark` - Dark mode blur background

### Spacing

Scale: 4px base unit
- `spacing[0]` = 0px
- `spacing[1]` = 4px
- `spacing[4]` = 16px
- `spacing[8]` = 32px
- Full scale available up to `spacing[96]` = 384px

### Blur

- `blur.base` = 12px (default)
- `blur.lg` = 20px (prominent)
- `blur.xl` = 24px (max)

### Transitions

**Spring Physics** (for interactive elements)
- `transitions.spring.gentle` - Slower, subtle
- `transitions.spring.default` - Standard
- `transitions.spring.snappy` - Faster, energetic
- `transitions.spring.bouncy` - Playful, overshoot

**Easing** (for non-spring animations)
- `transitions.ease.in` - Ease in (300ms)
- `transitions.ease.out` - Ease out (300ms)
- `transitions.ease.inOut` - Ease in-out (300ms)
- `transitions.ease.custom` - Premium easing (300ms)

---

## Component Variants

### BaseButton

**Variants:**
- `primary` - Gradient, main action
- `secondary` - Neutral background
- `ghost` - Text only
- `danger` - Red, destructive action
- `success` - Green, positive action

**Sizes:**
- `sm` - Small padding, text-sm
- `md` - Medium padding (default), text-base
- `lg` - Large padding, text-lg
- `xl` - Extra large padding, text-lg

**Props:**
- `isLoading` - Shows spinner, disables interaction
- `disabled` - Dims button, prevents click
- `fullWidth` - 100% width
- `icon` - Icon component from Lucide or Phosphor
- `iconPosition` - 'left' (default) or 'right'

### BaseCard

**Props:**
- `glassy` - Glassmorphic effect with blur (default: true)
- `gradient` - Gradient background
- `interactive` - Hover effects
- `padding` - sm | md | lg | xl | none (default: md)
- `rounded` - sm | md | lg | xl | full (default: lg)
- `shadow` - none | sm | base | md | lg | xl (default: base)
- `hover` - lift | scale | glow | none (default: lift)

### BaseInput

**Props:**
- `label` - Floating label text
- `error` - Error message (shows red border + message)
- `icon` - Icon component
- `type` - input type (default: text)
- `size` - sm | md | lg (default: md)
- `fullWidth` - 100% width
- `disabled` - Prevents input

---

## Animation Presets

### Entrances
- `fadeIn` - Opacity only
- `slideInUp` - Fade + Y translate from bottom
- `slideInDown` - Fade + Y translate from top
- `slideInLeft` - Fade + X translate from left
- `slideInRight` - Fade + X translate from right
- `scaleIn` - Fade + scale from small

### Hover Effects
- `hoverLift` - Y -4px with spring physics
- `hoverLiftSmall` - Y -2px
- `hoverLiftLarge` - Y -8px
- `hoverScale` - Scale 1.05 with spring
- `hoverScaleSmall` - Scale 1.02
- `hoverGlow` - Box-shadow glow

### Loading States
- `pulse` - Opacity oscillation (infinite)
- `shimmer` - Background position shift (infinite)
- `spin` - Rotation 360° (infinite)

### Interactive
- `buttonTap` - Y -1px + scale 0.98 on press
- `buttonHover` - Y -2px + scale 1.02 on hover

### Scroll Reveals
- `viewportReveal` - Fade + Y translate on viewport entry
- `viewportRevealStagger(index)` - Same + staggered delay

---

## Dark Mode

All components automatically support dark mode via:

1. **CSS Variables** - Automatically switch based on `prefers-color-scheme`
2. **Tailwind `dark:` Variant** - Base components use `dark:` prefixes
3. **Explicit Theme Toggle** - Set `data-theme="dark"` on `<html>` for manual override

### Testing Dark Mode

```bash
# Enable in DevTools (Chrome > F12 > Settings > Preferences > Appearance)
# Or use Inspect Element and right-click <html> to edit data-theme attribute
```

---

## Accessibility

### Built-in Features
- ✅ Focus rings on all interactive elements (2px indigo)
- ✅ WCAG AA contrast ratios in both light/dark modes
- ✅ Reduced motion support (animations skip if enabled)
- ✅ Semantic HTML (labels on inputs, proper heading levels)
- ✅ Keyboard navigation (tab order, enter/space to activate)

### Testing
```jsx
// Reduced motion
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Testing focus
// Use Tab key to navigate, Shift+Tab to go backward
// Focus ring should be visible on all buttons, inputs, links

// Testing dark mode
// DevTools > Settings > Appearance > Dark mode
```

---

## File Structure

```
src/
├── styles/
│   ├── tokens.js          # Design token definitions
│   └── globals.css        # Global styles, CSS variables
├── animations/
│   └── index.js           # Framer Motion presets
├── components/
│   └── ui/
│       ├── BaseButton.jsx # Button component
│       ├── BaseCard.jsx   # Card component
│       ├── BaseInput.jsx  # Input component
│       └── index.js       # UI exports
├── utils/
│   └── cn.js              # Class merging utility
└── index.css              # Imports globals.css
```

---

## Next Steps (Phase 2-6)

### Priority 1: Page Redesigns
- [ ] LoginPage → Premium asymmetric split
- [ ] AnalyzePage → Enhanced upload flow
- [ ] ReportDashboard → Animated metrics

### Priority 2: Component Enhancements
- [ ] AppNavbar → Glassmorphic, scroll blur
- [ ] ThemeToggle → Animated sun/moon icon
- [ ] Dropzone → Drag-over glow animation

### Priority 3: Advanced Pages
- [ ] SignupPage → Multi-step wizard
- [ ] HistoryPage → Premium table/cards
- [ ] ProfilePage → Tabbed settings dashboard

### Quality Assurance
- [ ] Lighthouse audit (90+ score target)
- [ ] Dark mode verification (all pages)
- [ ] Mobile responsiveness (320px+)
- [ ] Keyboard navigation (full tab flow)
- [ ] Reduced motion (animations skip)

---

## Common Patterns

### Staggered List Animation

```jsx
<motion.div {...staggerContainer}>
  {items.map((item, i) => (
    <motion.div key={item.id} {...staggerChild}>
      {item.content}
    </motion.div>
  ))}
</motion.div>
```

### Loading Button

```jsx
<BaseButton isLoading={isSubmitting}>
  {isSubmitting ? 'Submitting...' : 'Submit'}
</BaseButton>
```

### Glassmorphic Container

```jsx
<BaseCard glassy gradient interactive>
  <h3>Featured</h3>
  <p>Premium content in glass container</p>
</BaseCard>
```

### Form with Floating Labels

```jsx
<BaseInput
  label="Email Address"
  type="email"
  placeholder="Enter email"
  error={emailError}
  icon={Mail}
/>
```

---

## Performance Notes

- ✅ Spring animations use GPU acceleration (`transform` + `opacity` only)
- ✅ No infinite loops on entrance (only on status indicators)
- ✅ Reduced motion support prevents performance issues
- ✅ Lazy-load animations with `whileInView` and `viewport.once: true`
- ✅ Component-level memoization on heavy re-renders

---

**Last Updated:** 2026-08-25  
**Status:** Phase 1 Complete - Ready for Phase 2 Page Redesigns
