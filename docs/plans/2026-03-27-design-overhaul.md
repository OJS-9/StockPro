# StockPro — Full Design Overhaul Plan
**Date:** 2026-03-27
**Branch:** design_overhaul
**Design Authority:** UI/UX Design Advisor (Candlekeep principles)

---

## Executive Summary

StockPro is a capable product wearing a rough costume. The current dark-only, stone-300-primary design reads as a prototype rather than a tool people trust with their investments. The goal of this overhaul is to close that gap: make the app feel as precise and confident as the data it presents.

The reference aesthetic is Linear / Vercel — meaning high-contrast text, generous whitespace, crisp borders, and light mode that does not feel like an afterthought. The palette is **pure monochrome** — black, white, and zinc grays only. The only color in the entire UI is green (gains) and red (losses), which pop dramatically against the neutral chrome.

### What Changes
- Full dual-mode (light + dark) design system replacing dark-only
- Pure monochrome palette — no color accent, CTAs use contrast (dark-on-light / light-on-dark)
- Green and red are the ONLY colors in the UI (reserved exclusively for financial signals)
- Typography consolidation — Inter everywhere (drop Nunito, Manrope, Noto Sans)
- Auth pages become consistent with base.html (no more amber-400 / Space Grotesk break)
- Nav gets a dark/light toggle with localStorage persistence
- Status indicators, loading states, and error patterns become systematic
- All status messages move off emoji-conditional classes to semantic CSS tokens

### What Stays
- Tailwind CDN delivery (no build step introduced)
- Material Symbols Outlined icon set
- `darkMode: "class"` already set in Tailwind config — just needs the toggle wired up
- Clerk auth integration
- Flask / Jinja2 template structure
- Existing URL routes and template inheritance hierarchy

---

## 1. Design System Specification

### 1.1 Color Palette

**Pure monochrome.** The current `stone-300` "primary" is replaced with nothing — CTAs and interactive elements use contrast inversion instead of a color accent. The only chromatic colors in the entire UI are green (gains) and red (losses). This makes financial signals the most visually prominent elements on every page.

#### Dark Mode Tokens

| Token name | Hex | Tailwind source | Role |
|---|---|---|---|
| `bg-base` | `#09090b` | zinc-950 | Page background |
| `bg-surface` | `#18181b` | zinc-900 | Cards, panels, inputs |
| `bg-raised` | `#27272a` | zinc-800 | Hover states, secondary surfaces, CTA buttons |
| `border` | `#3f3f46` | zinc-700 | Card borders, dividers |
| `border-subtle` | `#27272a` | zinc-800 | Subtle separators inside cards |
| `text-primary` | `#fafafa` | zinc-50 | Headlines, primary text |
| `text-secondary` | `#a1a1aa` | zinc-400 | Labels, timestamps, metadata |
| `text-muted` | `#71717a` | zinc-500 | Placeholder, disabled |
| `cta-bg` | `#fafafa` | zinc-50 | CTA button background (inverted) |
| `cta-text` | `#09090b` | zinc-950 | CTA button text (inverted) |
| `cta-hover` | `#d4d4d8` | zinc-300 | CTA hover background |
| `gain` | `#22c55e` | green-500 | Positive P&L, buy actions |
| `loss` | `#ef4444` | red-500 | Negative P&L, sell/delete |

#### Light Mode Tokens

| Token name | Hex | Tailwind source | Role |
|---|---|---|---|
| `bg-base` | `#ffffff` | white | Page background |
| `bg-surface` | `#fafafa` | zinc-50 | Cards, panels |
| `bg-raised` | `#f4f4f5` | zinc-100 | Hover states, secondary surfaces |
| `border` | `#e4e4e7` | zinc-200 | Card borders, dividers |
| `border-subtle` | `#f4f4f5` | zinc-100 | Subtle separators |
| `text-primary` | `#09090b` | zinc-950 | Headlines |
| `text-secondary` | `#71717a` | zinc-500 | Labels, metadata |
| `text-muted` | `#a1a1aa` | zinc-400 | Placeholder, disabled |
| `cta-bg` | `#18181b` | zinc-900 | CTA button background (inverted) |
| `cta-text` | `#fafafa` | zinc-50 | CTA button text (inverted) |
| `cta-hover` | `#3f3f46` | zinc-700 | CTA hover background |
| `gain` | `#16a34a` | green-600 | Positive P&L (darker for WCAG on white) |
| `loss` | `#dc2626` | red-600 | Negative P&L |

**No warning/amber token.** Warning banners use `text-secondary` with a border — no color needed. Error banners use `loss`. Success banners use `gain`.

#### Tailwind Config Extension (to replace current config in base.html)

```js
tailwind.config = {
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                // Semantic tokens — reference these in templates
                "base":       { DEFAULT: "#ffffff", dark: "#09090b" },
                "surface":    { DEFAULT: "#fafafa", dark: "#18181b" },
                "raised":     { DEFAULT: "#f4f4f5", dark: "#27272a" },
                "edge":       { DEFAULT: "#e4e4e7", dark: "#3f3f46" },
                "cta":        { DEFAULT: "#18181b", dark: "#fafafa" },
                "cta-text":   { DEFAULT: "#fafafa", dark: "#09090b" },
                "cta-hover":  { DEFAULT: "#3f3f46", dark: "#d4d4d8" },
                "gain":       { DEFAULT: "#16a34a", dark: "#22c55e" },
                "loss":       { DEFAULT: "#dc2626", dark: "#ef4444" },
                // Keep existing tokens during migration (remove after all templates updated)
                "primary":          "#fafafa",
                "background-light": "#ffffff",
                "background-dark":  "#09090b",
                "surface-dark":     "#18181b",
                "border-dark":      "#3f3f46",
                "accent-up":        "#22c55e",
                "accent-down":      "#ef4444",
            },
            fontFamily: {
                "display": ["Inter", "sans-serif"],
                "body":    ["Inter", "sans-serif"],
            },
            borderRadius: {
                DEFAULT: "0.5rem",
                "sm":   "0.375rem",
                "md":   "0.5rem",
                "lg":   "0.75rem",
                "xl":   "1rem",
                "2xl":  "1.25rem",
                "full": "9999px",
            },
            boxShadow: {
                "card":    "0 1px 3px 0 rgb(0 0 0 / 0.05), 0 1px 2px -1px rgb(0 0 0 / 0.05)",
                "card-md": "0 4px 6px -1px rgb(0 0 0 / 0.07), 0 2px 4px -2px rgb(0 0 0 / 0.07)",
                "card-lg": "0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.08)",
            },
        },
    },
}
```

### 1.2 Typography

**Decision: Replace all font families with Inter only.**

Rationale (Principle 6 — Minimal Cognitive Load): Nunito, Manrope, and Noto Sans are all loaded from Google Fonts CDN but create no visual system — they appear inconsistently across templates. Inter is a purpose-built UI font optimized for screens, financial data tables, and compact labels. It reads cleanly at every size from 11px (transaction rows) to 48px (portfolio totals). Using one font family eliminates the "display vs body" class distinction and simplifies every template.

| Role | Size | Weight | Line height | Usage |
|---|---|---|---|---|
| Hero heading | `text-4xl` / `text-5xl` | `font-bold` (700) | `leading-tight` | Landing page H1 |
| Page title | `text-2xl` | `font-semibold` (600) | `leading-snug` | Page H1 (`Portfolios`, `AI Agent`) |
| Section heading | `text-lg` | `font-semibold` | `leading-snug` | Card headings, section titles |
| Body | `text-sm` | `font-normal` (400) | `leading-relaxed` | All paragraph text |
| Label | `text-xs` | `font-medium` (500) | `leading-normal` | Form labels, table column headers |
| Data / mono | `text-sm font-mono` | `font-medium` | `leading-none` | Prices, quantities, percentages |
| Caption | `text-xs` | `font-normal` | `leading-normal` | Timestamps, secondary metadata |

**Font loading (one CDN call, replace current three):**
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
```

### 1.3 Spacing System

Use Tailwind's default 4px grid. No custom spacing tokens needed. Key layout conventions:

- Page max-width: `max-w-7xl` with `px-4 md:px-8` side padding
- Section vertical rhythm: `py-8` between major sections, `space-y-6` within a section
- Card internal padding: `p-5` (standard), `p-4` (compact, e.g. table-style cards)
- Grid gaps: `gap-4` (tight grids), `gap-6` (standard), `gap-8` (section-level)

### 1.4 Border Radius System

Moving from rounded-3xl everywhere (overdone, juvenile for a financial tool) to a tighter, more Linear-like system:

| Class | Value | Usage |
|---|---|---|
| `rounded` / `rounded-md` | 6–8px | Buttons, badges, inputs, table cells |
| `rounded-lg` | 12px | Cards (standard) |
| `rounded-xl` | 16px | Modal containers, search bar, hero card |
| `rounded-full` | pill | Avatar circles only |

This creates a clear hierarchy: inputs/buttons are most square, modals and large containers are most rounded.

### 1.5 Shadow System (Light Mode)

Dark mode uses borders for depth. Light mode needs shadows for the same purpose.

```
card default:     shadow-card    (very subtle, 1px shadow)
card hover/focus: shadow-card-md (4px spread)
modals/dropdowns: shadow-card-lg (10px spread)
```

In dark mode all `shadow-*` classes reduce to invisible (dark surfaces use border contrast instead). Achieve this with: `shadow-card dark:shadow-none border border-edge dark:border-edge`.

### 1.6 Dark/Light Mode Toggle

**Implementation strategy: class-based via `darkMode: "class"` (already configured)**

The `<html>` element class controls mode. Toggle logic:

```js
// In base.html <head>, before Tailwind loads:
(function () {
    const stored = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (stored === 'dark' || (!stored && prefersDark)) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
})();
```

Toggle button (lives in nav, see Section 2):
```js
function toggleTheme() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
}
```

Default: respect system preference (`prefers-color-scheme`) on first visit. Persist user choice in `localStorage`.

---

## 2. Navigation Redesign

### Decision: Keep top horizontal nav, not sidebar

**Rationale:** Sidebars work for apps with deep hierarchies (20+ sections, nested navigation). StockPro has 5 top-level destinations. A sidebar would waste horizontal real estate on every page, particularly on the data-dense portfolio and chat pages. A clean, minimal top bar is the correct choice for this app's information architecture.

### New Nav Anatomy

```
[Logo + wordmark]  [Markets] [Reports] [AI Agent] [Portfolio] [Watchlist]     [mode-toggle] [avatar/auth]
```

**Changes from current nav:**
1. Add dark/light mode toggle between nav links and auth buttons — uses a sun/moon icon, no text label needed
2. Replace pill-shaped auth buttons (rounded-full) with text links — reduces visual weight in the header
3. Username display moves into a compact dropdown (avatar initials circle) rather than plain text
4. Active state changes from `text-primary font-bold` to an underline indicator (`border-b-2 border-cta`) — more Linear-like
5. Nav background: `bg-base/90 dark:bg-base/90 backdrop-blur-md` — same blur, updated tokens
6. Remove redundant `font-display` class from nav (all Inter now)

**Mode toggle button:**
```html
<button onclick="toggleTheme()" class="p-2 rounded-md text-secondary hover:text-primary hover:bg-raised transition-colors" aria-label="Toggle theme">
    <!-- Sun icon (shown in dark mode to switch to light) -->
    <span class="material-symbols-outlined dark:block hidden text-xl" style="font-size:20px">light_mode</span>
    <!-- Moon icon (shown in light mode to switch to dark) -->
    <span class="material-symbols-outlined dark:hidden block text-xl" style="font-size:20px">dark_mode</span>
</button>
```

**Auth state — authenticated:**
- Avatar circle: `size-8 rounded-full bg-raised text-primary font-semibold text-xs flex items-center justify-center` showing initials
- Clicking opens a minimal dropdown: Profile link + Sign Out

**Auth state — unauthenticated:**
- `Sign In` as text link, `Sign Up` as a small filled button (`bg-cta text-cta-text px-3 py-1.5 rounded-md text-sm font-medium`)

**Mobile (unchanged structure, updated tokens):**
- Hamburger opens right-side drawer
- Mode toggle appears at the top of the drawer panel

---

## 3. Page-by-Page Redesign Spec

### 3.1 Auth Pages — sign_in.html / sign_up.html

**Current problem:** These extend `base.html` but render a dark-only background (`bg-background-dark`), have no mode toggle, and use the Clerk-mounted component which inherits Clerk's own theme variables. The inconsistency isn't actually typography/color at this point (since Clerk renders its own UI) — it's the chrome around the Clerk widget.

**What changes:**
- Use `bg-base dark:bg-base` instead of hardcoded `bg-background-dark`
- Add the nav (include `_nav.html`) so the mode toggle is available on the auth screen
- Remove the standalone logo/wordmark below nav (redundant with nav logo)
- Center layout: `min-h-[calc(100vh-64px)] flex items-center justify-center`
- Clerk widget container: `bg-surface dark:bg-surface border border-edge dark:border-edge rounded-xl p-2` (same tokens as rest of app)
- Tell Clerk to use `appearance.baseTheme` if the Clerk JS version supports it — this is optional and shouldn't be a blocker

**Layout after change:**
```
[Nav with mode toggle]
[centered container: Clerk sign-in widget]
```

This eliminates the visual break when navigating from the landing page to sign-in.

---

### 3.2 Portfolio List — portfolio_list.html

**Current state:** Functional. Summary stat cards at top, then a table of portfolios. Main issues: status messages use emoji in Jinja conditionals (`{% if '❌' in status_message %}`), cards use `rounded-xl` inconsistently, no visual hierarchy difference between the recap row and the portfolio cards.

**Layout structure (keep, refine):**

```
[Page header: "Portfolios" H1 + "New Portfolio" button]
[Status message if present]
[Overall recap — horizontal stat row: Total Value | Total Cost Basis | Total Holdings | Portfolio Count]
[Portfolio cards grid (2-col on md, 1-col on sm)]
[Empty state if no portfolios]
[Create portfolio modal]
```

**Key changes:**

1. **Status messages** — replace emoji-conditional classes with semantic data attributes:
   ```html
   <div class="status-banner" data-type="error|warning|success">
   ```
   CSS: `.status-banner[data-type="error"] { @apply bg-loss/10 border border-loss/30 text-loss; }`
   This removes emoji from Python-side message strings and makes status handling consistent across all pages.

2. **Recap cards** — change from `rounded-xl` cards to a single horizontal rule-separated row inside one card:
   ```
   [Total Value: $xx,xxx] | [Cost Basis: $xx,xxx] | [Holdings: 12] | [Portfolios: 3]
   ```
   Single `bg-surface border border-edge rounded-lg p-5` container with `grid grid-cols-2 md:grid-cols-4 divide-x divide-edge` inside. More compact, linear-style.

3. **Portfolio cards** — change from table rows to cards with more data density:
   ```
   [Portfolio Name (bold)]    [Value (large, right-aligned)]
   [X holdings]               [P&L: +$xxx (+x.x%)]
   ```
   Interactive card: `hover:border-cta/40 hover:shadow-card-md cursor-pointer transition-all`

4. **"New Portfolio" button** — `bg-cta text-cta-text px-4 py-2 rounded-md text-sm font-medium` (replace current `bg-primary text-background-dark rounded-xl`)

5. **Create modal** — keep structure, apply new border radius (`rounded-xl`) and token classes

---

### 3.3 Portfolio Detail — portfolio.html

**Current state:** 4 summary stat cards + holdings table. Main issues: "Add Transaction" button uses `bg-accent-up` (green) — this should be primary/accent, not a gain indicator. Green for "add" conflates financial up-trend with a neutral action. Also the stat cards are vertically padded generously but offer no visual grouping.

**Layout structure:**

```
[Breadcrumb: < Portfolios / Portfolio Name]
[Page header row: Portfolio Name | [Add Transaction] [Import CSV]]
[Status message if present]
[Summary strip: Total Value | Cost Basis | Gain/Loss | Return %]
[Holdings table]
[Empty holdings state]
```

**Key changes:**

1. **"Add Transaction" button** — change to `bg-cta text-cta-text` (not green). Green is reserved for gain indicators. This is a neutral action.

2. **Summary strip** — same single-container grid pattern as portfolio list recap. The gain/loss card should dynamically apply `text-gain` or `text-loss` to the value, not to the entire card background.

3. **Holdings table** — shift from card-per-row to a proper `<table>` with:
   - `thead` with sticky positioning: `sticky top-[64px]` (height of nav)
   - Column headers: Symbol | Quantity | Avg Cost | Current Price | Market Value | Gain/Loss | Return %
   - Rows: `hover:bg-raised cursor-pointer transition-colors`
   - Price cells: `font-mono text-right`
   - Gain/Loss cells: conditional `text-gain` / `text-loss` class on value text only, not row background
   - Loading skeleton for current price column (since it fetches async)

4. **Empty state** — center-aligned, icon + heading + CTA, inside the table container area

5. **Breadcrumb** — `text-secondary text-sm` / `hover:text-primary` with `chevron_right` separator

---

### 3.4 Holding Detail — holding_detail.html

**Current state:** 4 stat cards + transaction table. Structurally sound. Issues: the asset icon container (orange for crypto, blue for stocks) uses ad-hoc colors `bg-orange-500/20` and `bg-blue-500/20` — these are undocumented one-offs.

**Layout structure:**

```
[Breadcrumb: < Portfolio Name / Symbol]
[Page header row: [asset icon + symbol + name] | [Add Transaction]]
[Summary strip: Quantity | Avg Cost | Current Price | Total Value | Gain/Loss | Return %]
[Transactions section header: "Transactions"]
[Transactions table]
```

**Key changes:**

1. **Asset icon** — replace ad-hoc orange/blue with design-system tokens:
   - Crypto: `bg-warn/15 text-warn` (amber — it's a risk asset, warm color appropriate)
   - Stock: `bg-raised text-primary` (neutral — consistent with monochrome system)

2. **Summary strip** — same single-container grid pattern, 3-col on sm, 6-col on md

3. **Transactions table** — a proper `<table>`:
   - Columns: Date | Type | Quantity | Price | Total | Notes | Actions
   - Buy row: Type badge `bg-gain/10 text-gain rounded text-xs px-2 py-0.5`
   - Sell row: Type badge `bg-loss/10 text-loss rounded text-xs px-2 py-0.5`
   - Delete action: `text-muted hover:text-loss transition-colors` (icon only, with confirm modal — no bright red button in every row)

4. **Delete confirm modal** — currently appears to be missing (direct link to delete route). Add a lightweight confirm modal rather than a direct destructive action link. Principle 7 (User Control): destructive actions need confirmation.

---

### 3.5 Chat / AI Research — chat.html

**Current state:** Message bubbles, research status area, input box. Main issues: both user and AI bubbles use the same `bg-surface-dark` — there is zero visual differentiation between sender and receiver. Input area doesn't strongly separate from message content.

**Layout structure:**

```
[Nav]
[Three-column layout on large screens: [context sidebar] [chat panel] (optional research preview)]
[Two-column on md: [chat panel fills width]]
```

Actually for simplicity, keep full-width single-column on all sizes with a max-width constraint.

```
[Nav]
[Main: flex-col, max-w-4xl mx-auto, full remaining height]
  [Messages area: flex-1 overflow-y-auto]
  [Input area: sticky bottom, bg-base border-t border-edge]
```

**Key changes:**

1. **Message differentiation:**
   - AI messages: `bg-surface border border-edge rounded-lg rounded-tl-sm` — left-aligned, standard card style
   - User messages: `bg-raised border border-edge rounded-lg rounded-tr-sm` — right-aligned, subtle surface differentiation
   - This restores Principle 1 (Transparency) — AI and user are visually distinct
   - Avatar for AI: `size-7 rounded-md bg-raised text-primary` with the `smart_toy` icon (16px)
   - Avatar for user: `size-7 rounded-md bg-raised` with initials

2. **Research status indicator** — when AI is processing, show a distinct "working" state inside the message bubble:
   ```
   [animated pulse bar] "Researching NVDA..."
   [animated pulse bar] "Analyzing earnings data..."
   ```
   Use `animate-pulse` on skeleton lines. This replaces a generic spinner and communicates *what* the AI is doing (Principle 3 — Feedback and Status Visibility).

3. **Input area:**
   ```html
   <div class="sticky bottom-0 bg-base dark:bg-base border-t border-edge px-4 py-4">
       <form class="flex gap-2 max-w-4xl mx-auto">
           <input ... class="flex-1 bg-surface border border-edge rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-zinc-400/30 focus:border-cta outline-none transition-all" />
           <button class="px-4 py-2.5 bg-cta text-cta-text rounded-lg text-sm font-medium hover:bg-cta-hover transition-colors">Send</button>
       </form>
   </div>
   ```
   No floating input — sticky-bottom with a top border makes the separation clear.

4. **Markdown output** — wrap AI markdown content in `prose dark:prose-invert prose-sm max-w-none` using Tailwind Typography if available, or keep the current `markdown-content` class with manual styles. Ensure heading sizes within markdown are constrained (no h1/h2 inside a chat bubble).

5. **Research popup modal** — keep existing logic, update styling to `rounded-xl bg-surface border border-edge shadow-card-lg`

---

### 3.6 Landing / Home — index.html

**Current state:** Hero card with SVG background, market overview pinned tickers, news section, recent reports. The hero is ~34KB total (large inline SVG). Structurally good.

**Key changes:**

1. **Hero section** — simplify:
   - Remove the inline grainy-gradient overlay (external URL, also adds visual noise)
   - Keep the SVG chart background but make it a clean two-shade version (reduce to two paths: a gain line and a loss line)
   - Hero container: `rounded-xl overflow-hidden` (was `rounded-2xl`)
   - Background blurs to a softer gradient: `bg-gradient-to-br from-zinc-200/30 via-base to-base dark:from-zinc-800/30 dark:via-base dark:to-base`

2. **Search bar** — minimal update:
   - `bg-surface border border-edge rounded-lg focus-within:ring-2 ring-zinc-400/30 focus-within:border-cta`
   - Replace current `rounded-xl` on the embedded select/button with `rounded-md`
   - "Analyze" button: `bg-cta text-cta-text` (not `bg-primary` stone-gray)

3. **Market Overview cards** — reduce from `rounded-3xl h-64` to `rounded-lg` cards with less decoration:
   - Remove the large blurred circle (`-right-10 -top-10 size-40 bg-accent-up/5 rounded-full blur-3xl`) — it is visual noise
   - Keep the sparkline SVG at the bottom — functional, looks good
   - Tighten from `p-6 h-64` to `p-5` with auto height

4. **Section headings** — `text-xl font-semibold` (not `text-3xl font-extrabold`) — a landing page for an app, not a marketing site

5. **Light mode** — the hero SVG background has both a dark and light variant already in the CSS (`.dark .hero-bg` and `.hero-bg`). Keep this, just update the token references to the new color system.

---

### 3.7 Watchlist — watchlist.html

**Current state:** Watchlist cards with symbol rows. At ~18KB this is a moderately complex template.

**Key changes:**

1. **Layout** — `max-w-5xl` centered, not full-width. Watchlists are list-heavy — they benefit from a narrower column.

2. **Symbol row** — compact table row style:
   ```
   [Symbol (bold, monospace)] [Company name (muted)] ... [Price] [Change %] [Pin toggle] [Remove]
   ```
   Row: `hover:bg-raised transition-colors border-b border-edge last:border-0`

3. **Pin toggle** — `text-muted hover:text-warn transition-colors` when unpinned, `text-warn` when pinned. Amber for "starred" items is a standard pattern.

4. **Section groups** — if the watchlist supports sections, use a subtle `text-xs font-medium uppercase tracking-wide text-muted` heading above each section group.

---

## 4. Component Library

These are the reusable patterns to establish in the codebase. Define them once in a comment block at the top of `base.html` or in a separate `_components.html` include that no template renders directly but serves as a reference.

### 4.1 Card Variants

```html
<!-- Card: Default -->
<div class="bg-surface dark:bg-surface border border-edge dark:border-edge rounded-lg p-5 shadow-card dark:shadow-none">

<!-- Card: Interactive (clickable) -->
<div class="bg-surface dark:bg-surface border border-edge dark:border-edge rounded-lg p-5 shadow-card dark:shadow-none hover:border-cta/40 hover:shadow-card-md cursor-pointer transition-all duration-150">

<!-- Card: Stat (compact KPI display) -->
<div class="bg-surface dark:bg-surface border border-edge dark:border-edge rounded-lg px-5 py-4">
    <p class="text-xs font-medium text-secondary mb-1.5">[Label]</p>
    <p class="text-2xl font-semibold font-mono text-primary">[Value]</p>
    <p class="text-xs text-secondary mt-1">[Sub-label or delta]</p>
</div>

<!-- Stat Strip (horizontal group of stat cards) -->
<div class="bg-surface dark:bg-surface border border-edge dark:border-edge rounded-lg grid grid-cols-2 md:grid-cols-4 divide-x divide-edge dark:divide-edge">
    <div class="px-5 py-4">...</div>
    <div class="px-5 py-4">...</div>
</div>
```

### 4.2 Button Variants

```html
<!-- Primary -->
<button class="inline-flex items-center gap-2 bg-cta text-cta-text px-4 py-2 rounded-md text-sm font-medium hover:bg-cta-hover transition-colors">

<!-- Secondary -->
<button class="inline-flex items-center gap-2 bg-surface border border-edge text-primary px-4 py-2 rounded-md text-sm font-medium hover:bg-raised transition-colors">

<!-- Ghost -->
<button class="inline-flex items-center gap-2 text-secondary px-4 py-2 rounded-md text-sm font-medium hover:bg-raised hover:text-primary transition-colors">

<!-- Destructive -->
<button class="inline-flex items-center gap-2 bg-loss/10 text-loss border border-loss/30 px-4 py-2 rounded-md text-sm font-medium hover:bg-loss/20 transition-colors">

<!-- Icon-only -->
<button class="p-2 rounded-md text-secondary hover:text-primary hover:bg-raised transition-colors">
```

**Note:** Remove all `rounded-full` buttons except avatar circles. Full-pill buttons read as marketing/consumer-app. The financial tool aesthetic is rectangular with mild radius.

### 4.3 Badge / Pill Variants

```html
<!-- Gain -->
<span class="inline-flex items-center gap-1 bg-gain/10 text-gain text-xs font-medium px-2 py-0.5 rounded">+2.4%</span>

<!-- Loss -->
<span class="inline-flex items-center gap-1 bg-loss/10 text-loss text-xs font-medium px-2 py-0.5 rounded">-1.1%</span>

<!-- Neutral / info -->
<span class="inline-flex items-center gap-1 bg-raised text-secondary text-xs font-medium px-2 py-0.5 rounded">ETF</span>

<!-- Trade type (Investment / Day Trade / Swing Trade) -->
<span class="inline-flex items-center bg-raised text-primary text-xs font-medium px-2 py-0.5 rounded">Investment</span>
```

### 4.4 Input / Form Fields

```html
<!-- Text input -->
<input type="text" class="w-full bg-surface border border-edge rounded-md px-3 py-2 text-sm text-primary placeholder:text-muted focus:ring-2 focus:ring-zinc-400/30 focus:border-cta outline-none transition-all">

<!-- Select -->
<select class="bg-surface border border-edge rounded-md px-3 py-2 text-sm text-primary focus:ring-2 focus:ring-zinc-400/30 focus:border-cta outline-none transition-all">

<!-- Form label -->
<label class="block text-xs font-medium text-secondary mb-1.5">

<!-- Form group -->
<div class="space-y-1.5">
    <label ...>Symbol</label>
    <input ...>
    <p class="text-xs text-muted">Optional help text</p>
</div>
```

### 4.5 Data Table

```html
<div class="rounded-lg border border-edge dark:border-edge overflow-hidden">
    <table class="w-full text-sm">
        <thead>
            <tr class="bg-raised dark:bg-raised border-b border-edge">
                <th class="text-left px-4 py-3 text-xs font-medium text-secondary uppercase tracking-wide">Symbol</th>
                <th class="text-right px-4 py-3 text-xs font-medium text-secondary uppercase tracking-wide">Value</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-edge dark:divide-edge">
            <tr class="hover:bg-raised dark:hover:bg-raised transition-colors cursor-pointer">
                <td class="px-4 py-3 font-medium text-primary">AAPL</td>
                <td class="px-4 py-3 text-right font-mono text-primary">$182.50</td>
            </tr>
        </tbody>
    </table>
</div>
```

### 4.6 Skeleton Loaders

Use for async price loading in portfolio and holding detail:

```html
<!-- Inline skeleton (single value) -->
<div class="h-6 w-24 bg-raised dark:bg-raised rounded animate-pulse"></div>

<!-- Row skeleton (for table loading state) -->
<tr>
    <td class="px-4 py-3"><div class="h-4 w-16 bg-raised rounded animate-pulse"></div></td>
    <td class="px-4 py-3 text-right"><div class="h-4 w-20 bg-raised rounded animate-pulse ml-auto"></div></td>
</tr>
```

Replace current `text-stone-500 animate-pulse` text content (e.g. `—`) with proper skeleton shapes. The `—` placeholder violates Principle 3 (Feedback and Status Visibility) — it looks like empty data, not a loading state.

### 4.7 Status / Alert Banners

Replace all emoji-conditional status messages across every template:

```html
<!-- Error -->
<div class="flex items-start gap-3 bg-loss/8 border border-loss/25 text-loss rounded-lg px-4 py-3 text-sm">
    <span class="material-symbols-outlined text-base flex-shrink-0 mt-0.5">error</span>
    <p>{{ status_message }}</p>
</div>

<!-- Warning -->
<div class="flex items-start gap-3 bg-warn/8 border border-warn/25 text-warn rounded-lg px-4 py-3 text-sm">
    <span class="material-symbols-outlined text-base flex-shrink-0 mt-0.5">warning</span>
    <p>{{ status_message }}</p>
</div>

<!-- Success -->
<div class="flex items-start gap-3 bg-gain/8 border border-gain/25 text-gain rounded-lg px-4 py-3 text-sm">
    <span class="material-symbols-outlined text-base flex-shrink-0 mt-0.5">check_circle</span>
    <p>{{ status_message }}</p>
</div>
```

The Flask route layer should pass a `status_type` variable (`"error"`, `"warning"`, `"success"`) alongside `status_message`. Templates select the variant by checking `status_type`, not by string-searching the message for emoji characters.

### 4.8 Modal

```html
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
    <div class="bg-surface border border-edge rounded-xl shadow-card-lg w-full max-w-md mx-4 p-6">
        <div class="flex items-center justify-between mb-5">
            <h2 class="text-base font-semibold text-primary">Modal Title</h2>
            <button class="p-1.5 rounded-md text-secondary hover:text-primary hover:bg-raised transition-colors">
                <span class="material-symbols-outlined text-base">close</span>
            </button>
        </div>
        <!-- content -->
        <div class="flex justify-end gap-2 mt-6">
            <button class="[secondary button]">Cancel</button>
            <button class="[primary button]">Confirm</button>
        </div>
    </div>
</div>
```

---

## 5. Implementation Order

Work in this exact sequence to ensure each step leaves the app in a functional state.

### Phase 1 — Foundation (base.html + _nav.html)
**Files:** `base.html`, `_nav.html`

1. **`base.html`** — Update Tailwind config with new color tokens (keep legacy aliases during migration). Replace font CDN link (one Inter call replaces three). Add theme initialization script in `<head>`. Update `<body>` class to `bg-base dark:bg-base text-primary dark:text-primary`. Update scrollbar CSS vars to new tokens.

2. **`_nav.html`** — Add mode toggle button with `toggleTheme()`. Update active state from `text-primary font-bold` to `text-primary border-b-2 border-cta` (needs `pb-0.5` on nav links). Replace pill auth buttons with text link + small filled button. Add avatar dropdown for authenticated state. Update all token class names to new system.

**Result:** Every page gets new fonts, mode toggle, and nav styling in one step. Verify light/dark toggle works and persists.

### Phase 2 — Auth Pages
**Files:** `sign_in.html`, `sign_up.html`

3. Add `{% include '_nav.html' %}` to both files. Remove hardcoded `bg-background-dark`. Update container tokens. Remove standalone logo section (already in nav). Verify Clerk widget renders correctly in both modes.

**Result:** Auth pages now feel like part of the same app.

### Phase 3 — Portfolio Flow
**Files:** `portfolio_list.html`, `portfolio.html`, `holding_detail.html`, `add_transaction.html`, `import_csv.html`

4. **`portfolio_list.html`** — Stat strip pattern, portfolio cards, fix status message pattern (remove emoji conditionals), update button to `bg-cta text-cta-text`.

5. **`portfolio.html`** — Stat strip, switch "Add Transaction" to `bg-cta text-cta-text`, apply table pattern for holdings, fix loading skeleton.

6. **`holding_detail.html`** — Stat strip, asset icon tokens (monochrome), transaction table, add delete confirm modal.

7. **`add_transaction.html`** — Apply form field patterns, update button.

8. **`import_csv.html`** — Apply form field patterns, drag-drop zone update.

**Result:** The entire portfolio flow is consistent.

### Phase 4 — Chat / AI Agent
**Files:** `chat.html`

9. Differentiate AI vs user message bubbles. Update input area to sticky-bottom pattern. Apply skeleton loader for AI working state. Update research popup modal. Ensure markdown styles work in both modes.

**Result:** Chat feels distinct and trust-signaling.

### Phase 5 — Landing + Supporting Pages
**Files:** `index.html`, `watchlist.html`, `reports.html`, `report_view.html`

10. **`index.html`** — Simplify hero, update search bar, reduce card decoration, update section headings.

11. **`watchlist.html`** — Apply table row pattern, pin toggle tokens, section group headings.

12. **`reports.html`** / **`report_view.html`** — Apply card and table patterns; report viewer should use `prose` styling for the markdown content.

**Result:** Full consistency across all pages.

### Phase 6 — Polish
13. Remove legacy token aliases from Tailwind config (the `primary`, `background-dark`, etc. kept for migration safety).
14. Update `static/css/style.css` note in CLAUDE.md — it remains unused and should stay that way.
15. Audit WCAG 2.1 AA contrast on all new text/background combinations (Principle 8).
16. Test all interactive states keyboard-only (tab, enter, escape on modals).

---

## 6. Known Inconsistencies Resolved by This Plan

| Issue | Current state | After overhaul |
|---|---|---|
| Auth pages visual break | standalone dark-only, amber-400 | extend base.html, use nav + monochrome tokens |
| No light mode | dark-only | full dual mode with persistent toggle |
| stone-300 "primary" | warm gray, low contrast | replaced with monochrome contrast-inversion CTAs |
| Status messages use emoji in conditionals | `{% if '❌' in status_message %}` | semantic `status_type` variable + variant classes |
| Loading skeleton shows `—` text | misleading, looks like empty data | proper `animate-pulse` skeleton shapes |
| "Add Transaction" uses green (gain color) | conflates action type with financial signal | updated to monochrome CTA (bg-cta) |
| Three font families loaded | Nunito + Manrope + Noto Sans + Inter | Inter only |
| Delete transaction has no confirm | direct destructive link | confirm modal |
| Rounded-3xl on everything | overdone for financial tool | tighter radius system |
| No dark/light toggle despite darkMode: "class" being set | toggle infrastructure exists, not wired | toggle button in nav + localStorage |

---

## Design Principles Traceability

| Decision | Principle |
|---|---|
| Differentiated AI vs user bubbles in chat | Principle 1 — Transparency and Trust |
| Skeleton loaders replace `—` placeholder | Principle 3 — Feedback and Status Visibility |
| Delete confirm modal | Principle 7 — User Control and Agency |
| Single font family (Inter) | Principle 6 — Minimal Cognitive Load |
| Persistent dark/light mode toggle | Principle 9 — Contextual Relevance |
| Semantic status banners (not emoji-conditional) | Principle 4 — Error Recovery and Graceful Degradation |
| Tighter border radius (less decoration) | Principle 10 — Delight Through Simplicity |
| Auth pages brought into base.html | Principle 5 — Consistency and Predictability |
| WCAG contrast audit in Phase 6 | Principle 8 — Accessibility First |
| Pure monochrome — green/red as only color | Principle 2 — Progressive Disclosure (financial signals are the most prominent visual element) |
