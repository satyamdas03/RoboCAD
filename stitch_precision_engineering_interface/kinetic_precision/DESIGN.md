---
name: Kinetic Precision
colors:
  surface: '#121315'
  surface-dim: '#121315'
  surface-bright: '#38393b'
  surface-container-lowest: '#0d0e10'
  surface-container-low: '#1b1c1e'
  surface-container: '#1f2022'
  surface-container-high: '#292a2c'
  surface-container-highest: '#343537'
  on-surface: '#e3e2e5'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#e3e2e5'
  inverse-on-surface: '#303033'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#ffd799'
  on-secondary: '#432c00'
  secondary-container: '#feb300'
  on-secondary-container: '#6a4800'
  tertiary: '#ffeac0'
  on-tertiary: '#3e2e00'
  tertiary-container: '#fec931'
  on-tertiary-container: '#6f5500'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#ffdeac'
  secondary-fixed-dim: '#ffba38'
  on-secondary-fixed: '#281900'
  on-secondary-fixed-variant: '#604100'
  tertiary-fixed: '#ffdf96'
  tertiary-fixed-dim: '#f3bf26'
  on-tertiary-fixed: '#251a00'
  on-tertiary-fixed-variant: '#594400'
  background: '#121315'
  on-background: '#e3e2e5'
  surface-variant: '#343537'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-base:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-xs:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 12px
  margin: 16px
  panel-padding: 8px
---

## Brand & Style

The design system is engineered for high-stakes robotics and industrial CAD environments. It evokes the feeling of a professional CNC workstation or a laboratory instrument: focused, immutable, and high-performance.

The aesthetic follows a **Modern Industrial** movement. It prioritizes information density over white space, utilizing tactical hardware metaphors like inset surfaces, micro-textures, and high-contrast diagnostic readouts. The interface is designed to remain legible in low-light laboratory settings while providing the millisecond-precision feedback required for real-time control.

## Colors

This design system utilizes a "Zero-G" dark palette to reduce eye strain during long engineering sessions.

- **Primary (Surgical Cyan):** Used strictly for active states, primary actions, and successful validation. It should feel like a glowing filament against the dark base.
- **Secondary (Tactical Amber):** Reserved for warnings, critical parameters, and caution-level alerts.
- **Surface Strategy:** Backgrounds use a deep charcoal (#0B0C0E). Successive layers of UI (panels, modals) use slightly lighter obsidian shades to create a "machined" depth without heavy shadows.
- **Semantic Accents:** Use a muted Crimson (#FF4D4D) only for terminal errors or emergency stops.

## Typography

Typography is treated as a functional readout. **Inter** provides high legibility for directional UI elements and navigation. **JetBrains Mono** is the "engine" font, used for all numerical inputs, status codes, coordinates, and system logs to ensure character alignment and a technical feel.

### Scaling Rules
On mobile devices, display titles scale down to 24px. The label and data sizes remain constant (11px-13px) to maintain the "high-density" requirement, as industrial users prioritize data visibility over touch-target padding.

## Layout & Spacing

The layout utilizes a **Fixed-Pane Grid** system inspired by IDEs and control rooms. 

- **Density:** We employ a tight 4px baseline grid. 
- **Structure:** Content is organized into modular "Panes." Each pane is separated by a 1px divider (#2D3139).
- **Reflow:** On desktop, the layout is multi-column (Sidebar / Main Viewport / Property Inspector). On tablet, the Property Inspector collapses into a drawer. On mobile, the interface switches to a stacked single-column view with a persistent status bar at the bottom.

## Elevation & Depth

This system avoids ambient shadows, opting for **Tonal Layering** and **Inset Borders** to convey hierarchy.

- **Panels:** Use a 0.5px or 1px solid border (#2D3139). 
- **Inset Fields:** Parameter inputs use a slightly darker background than their parent panel and a "top-inner-shadow" effect to look recessed into the "dashboard."
- **Glow Effects:** Active states or "Back-end Online" indicators use a soft 4px-8px outer glow of the primary color (#00E5FF) at 30% opacity to simulate LED indicators.

## Shapes

The shape language is "Soft-Industrial." 

- **Base Radius:** 4px (0.25rem) for almost all containers and buttons to maintain a precise, non-organic look.
- **Interactive Elements:** Buttons and inputs follow the 4px rule.
- **Inner Elements:** When nesting elements (like a chip inside an input), the inner radius is reduced to 2px to maintain visual concentricity.

## Components

### Buttons
- **Primary:** Solid Cyan (#00E5FF) with black text. On hover, apply a subtle inner-glow.
- **Secondary/Ghost:** 1px border (#2D3139) with a micro-textured background (diagonal 1px lines at 5% opacity).
- **Active State:** Border shifts to Cyan; text remains High-Contrast White.

### Input Fields (Parameters)
- **Style:** Inset appearance with monospaced text.
- **Units:** Fixed labels (e.g., "mm", "deg") are right-aligned within the field in a muted secondary text color.

### Chips & Status Tags
- **Validation Tags:** Small, rectangular tags with 2px corners. "Success" uses a Cyan border; "Warning" uses an Amber border.

### Terminal/Logs
- **Background:** Pure black (#000000).
- **Text:** JetBrains Mono. Timestamp in muted gray, message in primary white, errors in high-visibility red.

### Checkboxes & Radios
- **Style:** Square-cornered (1px radius). When checked, they fill with Cyan and a "center-dot" rather than a checkmark for a more instrument-like appearance.