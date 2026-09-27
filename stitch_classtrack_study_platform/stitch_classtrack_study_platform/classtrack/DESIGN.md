---
name: ClassTrack
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#006e2f'
  on-secondary: '#ffffff'
  secondary-container: '#6bff8f'
  on-secondary-container: '#007432'
  tertiary: '#784b00'
  on-tertiary: '#ffffff'
  tertiary-container: '#996100'
  on-tertiary-container: '#ffeedd'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#6bff8f'
  secondary-fixed-dim: '#4ae176'
  on-secondary-fixed: '#002109'
  on-secondary-fixed-variant: '#005321'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.025em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.011em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: -0.006em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: -0.01em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-sm: 1rem
  margin: 2rem
  margin-sm: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style
The design system pairs high-utility engineering rigor with playful, habit-forming mechanics. Built for cohort-based bootcamps and intensive technical learning squads (e.g., 100 Days of Code), the aesthetic merges the structured density of GitHub and Linear, the clean document-first calm of Notion, and the motivational frictionlessness of Duolingo. 

The emotional signature is dependable, focused, and momentum-driven. The interface avoids frivolous clutter while honoring micro-milestones—streaks, committed tasks, and peer accountability—through tactile state feedback and crisp visual ergonomics.

### Design Movement
- **Productive Pragmatism:** Modern SaaS foundation with precise structural borders, generous negative space, neutral canvas framing, and high-legibility typographic hierarchies.
- **Micro-Gamification:** Rich functional accents (amber streaks, emerald completions) elevated above a clean monochrome base to direct visual energy toward progress and peer benchmarks without degrading into distraction.

## Colors
The system employs an intentional hierarchy anchored by a high-clarity Slate spectrum and punctuated by focused semantic pigments:

- **Primary (`#2563EB` / Royal Blue):** Used for authoritative actions, selected states, progress indicators, and active cohort controls.
- **Secondary / Success (`#22C55E` / Emerald Green):** Denotes completed challenges, passed assertions, positive delta trends, and activity grid density.
- **Tertiary / Streak (`#F59E0B` / Amber Gold):** Dedicated to streak counts, trophy markers, active momentum states, and leaderboard podiums.
- **Neutral Primary (`#0F172A` / Slate 900):** Deep structural slate reserved for high-priority typography, sharp icon fills, and key framing lines.
- **Neutral Secondary (`#64748B` / Slate 500):** Intermediate slate for meta labels, table headers, supporting details, and inactive controls.
- **Surface Canvas (`#F8FAFC` / Slate 50):** Off-white base creating soft contrast for cards and modules.
- **Surface Card (`#FFFFFF` / Pure White):** Clean elevated surface for cards, modals, and interactive modules.
- **Dividers & Borders (`#E2E8F0` / Slate 200):** Ultra-crisp, non-obtrusive delineation for grid lines and structural containers.

## Typography
Typographic rhythm relies on `Inter` for interface structure, cohort data, and editorial clarity, augmented by `JetBrains Mono` for developer data, metrics, code snippets, and commit hashes.

- **Display & Section Headers:** High-contrast weights with negative tracking (`-0.025em` to `-0.015em`) enforce visual grouping and high-density scannability.
- **Body & Data:** Standard baseline heights ensure vertical cadence aligns neatly across 4px-driven layouts.
- **Monospaced Identifiers:** All tags, task counts, commit IDs, and tabular figures utilize `JetBrains Mono` with uppercase tracking where appropriate to preserve vertical column alignment in dense tables and dashboards.

## Layout & Spacing
The layout follows an adaptive 12-column grid anchored to an 8px base spacing grid (with 4px half-steps for compact UI controls).

- **Desktop (>= 1280px):** 12-column grid with `margin: 2rem` and `gutter: 1.5rem`. Max layout container width is 1440px to retain scan efficiency for data tables and task boards.
- **Tablet (768px - 1279px):** 8-column layout with `gutter: 1rem` and `margin: 1.5rem`. Multi-pane views (e.g., Code Runner + Cohort Feed) switch to vertical stack or collapsible split-views.
- **Mobile (< 768px):** 4-column layout with `margin: 1rem` and `gutter: 1rem`. Kanban columns transition to swipable carousels; leaderboards reduce secondary columns to display rank, user, and streak metric only.

## Elevation & Depth
Depth is produced through subtle layered containment rather than high-contrast drops:

- **Surface Base:** Light gray canvas (`#F8FAFC`) creates immediate separation from elevated white cards (`#FFFFFF`).
- **Low-Contrast Outlines (Structural Restraint):** All elevated elements integrate an ultra-fine border ring: `box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.06)`.
- **Resting Elevation:** Cards, popovers, and containers use `box-shadow: 0 1px 2px 0 rgba(15, 23, 42, 0.04), 0 0 0 1px rgba(15, 23, 42, 0.05)`.
- **Hover/Interactive Lift:** Interactive cards, draggable Kanban tasks, and active dropdowns transition smoothly (`150ms ease-out`) to: `box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05), 0 0 0 1px rgba(15, 23, 42, 0.08)`.
- **Overlays & Modals:** Deep ambient diffusion with `box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.08)` backed by a backdrop blur (`backdrop-filter: blur(4px) bg-slate-900/20`).

## Shapes
The design adopts a generous, balanced curvature to soften technical data:

- **Cards & Primary Modules:** Standardized to `16px` (`rounded-lg` token at scale `2`), conveying friendly, touch-accessible cohesion across desktop and mobile.
- **Interactive Controls (Buttons, Inputs, Selects):** Standardized to `8px` (`0.5rem`) for a precise, tool-grade feel.
- **Pills & Status Micro-Elements:** Fully rounded `9999px` (circular pills) for streak counters, tags, and category chips.
- **Contribution Matrix Units:** Rounded corners at `3px` with `3px` gaps, echoing classic developer contribution graphs.

## Components

### Buttons
- **Primary:** Solid `#2563EB`, text `#FFFFFF`, rounded 8px, height 38px, padding 0 16px. Subtle top highlight (`inset 0 1px 0 rgba(255,255,255,0.15)`), hover state `#1D4ED8`.
- **Secondary:** Surface `#FFFFFF`, border `1px solid #E2E8F0`, text `#0F172A`, hover `#F8FAFC`.
- **Ghost/Tertiary:** No border, text `#64748B`, hover `#F1F5F9` with text `#0F172A`.

### Streak Counters & Podium Elements
- **Streak Counter:** Amber pill container (`#FEF3C7`), text `#B45309`, flame icon in `#F59E0B`. Number formatted in `JetBrains Mono` bold.
- **Leaderboard Podium:** Top 3 ranks feature metallic tint rings (`#F59E0B` for 1st, `#94A3B8` for 2nd, `#D97706` for 3rd) with an avatar elevation frame and pill place badge centered on the bottom border.

### Contribution Grid (Heatmap)
- 7-row matrix representing days of the week. Cells: `10px x 10px`, radius `2px`.
- Levels: Level 0 (`#E2E8F0`), Level 1 (`#DCFCE7`), Level 2 (`#86EFAC`), Level 3 (`#22C55E`), Level 4 (`#15803D`).
- Tooltip displays date, total tasks solved, and pass rate on hover.

### Progress Gauges (Circular)
- SVG ring indicators with track stroke `#E2E8F0` (width 6px) and active stroke `#2563EB` or `#22C55E` with `stroke-linecap: round`.
- Center label displays numeric percentage or fraction formatted with `JetBrains Mono`.

### Kanban Task Columns
- Column header features title, count pill (`#F1F5F9`, text `#475569`), and swift action icon.
- Cards inside column: Pure white background, `12px` padding, `1px solid #E2E8F0`, rounded `10px`, containing priority chip, task title, and assignee avatars with overlapping -6px margin.

### Code Editor Mockup
- Framed window with header bar featuring three terminal dots (`#EF4444`, `#F59E0B`, `#10B981`) and file name in `JetBrains Mono` 12px.
- Background `#0F172A`, text `#F8FAFC`, line numbers in `#475569`. Integrated status footer indicating compilation status with a mini `#22C55E` beacon.

### Form Inputs & Checkboxes
- **Inputs:** Height 40px, border `1px solid #E2E8F0`, pure white surface, inner text `#0F172A`, placeholder `#94A3B8`. Focus ring: `0 0 0 2px rgba(37, 99, 235, 0.2)`.
- **Checkboxes:** 18px square, 4px radius, border `1.5px solid #CBD5E1`. Checked state transitions to `#22C55E` fill with an animated white SVG checkmark.