# Mobile Audit Missions (375px)

Audit of StockPro React SPA at iPhone viewport (375×812) after Phase 2 mobile polish. Screenshots in this folder.

## Summary of horizontal overflow

| Page | scrollWidth | Status |
|---|---|---|
| Home | 375 | Fixed this session (minWidth:0 on grid LEFT column) |
| Reports | 375 | OK, two UI polish issues |
| Alerts | 375 | OK |
| Portfolio list | 375 | Stats row overflows intentionally; cards squished |
| Research wizard | 375 | OK |
| Watchlist | 375 | OK |
| Settings | 375 | **BROKEN** — sidebar layout clips content panel |
| Portfolio detail | 375 | Fixed this session (minWidth:0 on grid LEFT column) |
| Holding detail | 375 | OK |
| Ticker page (`/ticker/:symbol`) | **659** | **BROKEN** — 2-col layout never stacks on mobile |

Two pages still overflow horizontally. Several others have content issues.

---

## Missions (ordered by severity)

### M1. Ticker page (`/ticker/:symbol`) — horizontal overflow
**File:** `stockpro-web/src/pages/TickerPage.tsx`
**Observed:** `documentElement.scrollWidth = 659` at 375px viewport. Screenshot `12-ticker-page.png` shows the page laid out as 2 columns: a main info+chart column and a right sidebar with key stats / report cards. The right column pokes ~284px off the right edge of the screen.
**Fix:** Find the outer grid that uses `gridTemplateColumns: '1fr 320px'` (or similar) and wire in `useBreakpoint`: `isMobile ? '1fr' : '1fr 320px'`. Also add `minWidth: 0` to the `1fr` grid child (same pattern as Home and PortfolioDetail fixes).

### M2. Settings (`/settings`) — sidebar + content never stacks
**File:** `stockpro-web/src/pages/Settings.tsx`
**Observed:** Screenshot `09-settings.png`. The left section-nav takes ~60% of the viewport; the right "Profile" content panel is clipped showing just "Profi…" and the subtitle partially. Settings nav and content must stack vertically on mobile.
**Fix:** Wrap the parent grid/flex in `useBreakpoint` so nav becomes a horizontal scroll strip or a select dropdown on mobile, and content renders full-width below it.

### M3. Portfolio list (`/portfolio`) — stats row clips, create-card squeezed
**File:** `stockpro-web/src/pages/PortfolioList.tsx`
**Observed:** Screenshot `04-portfolio-list.png`. Top stats row has 4 cards (Total Value / Total P&L / Today's Change / Portfolios) laid out horizontally and overflowing — user sees only the first 1.5 cards. Below, the portfolio card + "Create a portfolio" card sit side-by-side in a 2-col grid and are narrow enough that the portfolio card's chart/value is clipped.
**Fix:**
- Stats row: wrap in `overflow-x: auto` with explicit card `minWidth`, OR stack to a 2×2 grid on mobile.
- Portfolio grid: `isMobile ? '1fr' : 'repeat(2, 1fr)'` (or whatever is current) so each card gets full width.

### M4. Reports list (`/reports`) — title wraps; filter chip clipped
**File:** `stockpro-web/src/pages/ReportsHistory.tsx`
**Observed:** Screenshot `02-reports.png`.
- "Research Reports" H1 wraps onto 2 lines because the "New Research" button sits to the right.
- Filter toggle (grid_view / list) on the right shows only half — label says "Tick" instead of "Tickers".
**Fix:**
- On mobile: stack the page header (title on its own row, action button below or inline-wrapped).
- Filter segmented control: shrink the label to icon-only on mobile, or reserve full width.

### M5. Home — research bar input placeholder truncates
**File:** `stockpro-web/src/pages/Home.tsx`
**Observed:** Screenshot `01-home.png`. Placeholder reads "Research any stock or cr…". Minor but noticeable.
**Fix (optional):** On mobile, swap to a shorter placeholder (`t('home.researchPlaceholderShort')` → "Ticker…") OR drop `whiteSpace: nowrap` on the Research button so it can condense. Not blocking.

### M6. Home — sparkline bleeds over day-change text
**File:** `stockpro-web/src/pages/Home.tsx` (Total Portfolio Value card)
**Observed:** The decorative sparkline in the bottom-right of the primary KPI card overlaps the "(+1.52%) today" line on mobile (card is narrower so the 120×60 sparkline area collides with text).
**Fix (optional):** `isMobile ? null : <Sparkline gain />` or shrink to 80×40 on mobile.

### M7. Ticker page — verify chart + key stats after M1
Once M1's grid stacks on mobile, re-screenshot to confirm the watchlist eye icon, sector pills row, and key stats grid all fit. Likely additional inline fontSize ternaries needed for the big "$69.19" price.

---

## Work this session (already done + committed separately)

- Added `minWidth: 0` to Home LEFT grid column (`stockpro-web/src/pages/Home.tsx` line ~233) — fixed holdings table forcing 600px page width.
- Added `minWidth: 0` to PortfolioDetail LEFT grid column (`stockpro-web/src/pages/PortfolioDetail.tsx` line ~205) — fixed chart SVG forcing 886px page width.

These two `minWidth: 0` fixes are the same pattern M1 will need on TickerPage.

## Verification checklist for each mission

1. Run `cd stockpro-web && npm run dev`.
2. Chrome DevTools at 375px OR run `playwright-cli resize 375 812`.
3. After fix, confirm `document.documentElement.scrollWidth === 375` (no horizontal page scroll).
4. Screenshot the page and eyeball: no content clipped beyond the viewport.
5. Re-test at 768px and 1280px to confirm no desktop regression.
