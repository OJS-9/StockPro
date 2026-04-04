# Research: BLMTRM GitHub Repository Analysis
**Date:** 2026-04-02
**Repo:** https://github.com/thompson0012/blmtrm
**Purpose:** Competitive/inspiration analysis for StockPro

---

## 1. What Is This Product?

BLMTRM is an open-source, browser-based Bloomberg Terminal clone. The tagline is "hacker-style Bloomberg Terminal" — it puts real-time market data, charts, news, economic indicators, portfolio analytics, stock screener, watchlist, price alerts, and an AI financial assistant all inside a single split-pane terminal UI in the browser.

It is MIT-licensed and designed for local self-hosting.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 7, Tailwind CSS 3, shadcn/ui |
| Charts | Recharts (main), Lightweight Charts (secondary) |
| Routing | Wouter (lightweight, hash-based) |
| Server state | TanStack React Query |
| Backend | Express 5, TypeScript 5.6 |
| Database | PostgreSQL + Drizzle ORM (optional; falls back to in-memory Maps) |
| AI | Anthropic Claude Sonnet via `@anthropic-ai/sdk` |
| Layout | `react-resizable-panels` |
| Video | Remotion 4 (for programmatic demo rendering only) |

### Data Sources (all free, no API key required for basic use)
- **Yahoo Finance** — primary equity quotes and OHLCV
- **Stooq** — fallback for quotes and history
- **CoinGecko** — crypto prices
- **CBOE CDN** — VIX data
- **RSS feeds** — CNBC, Google News, CoinDesk for news

---

## 3. Key Features

### Market Intelligence
- Real-time stock quotes with freshness indicators and source attribution
- Candlestick / line / area charts with timeframes from 5m to 2Y
- Technical indicators: SMA20, SMA50, RSI(14)
- Multi-symbol comparison overlay on charts (up to 2 extra symbols, normalized)
- Volume sub-panel
- Market overview: gainers, losers, most active, sentiment
- Financial news feed with article reader and source tracking
- Economic indicators dashboard + event calendar
- Stock screener filtered by sector and P/E ratio
- Peer comparison (up to 6 competitors) inside quote view

### Portfolio and Alerts
- Watchlist (CRUD) with persistent storage
- Price alerts: above/below triggers with automatic monitoring via `alertsEngine.ts`
- Portfolio analytics: position tracking, P&L, allocation, benchmark comparison

### AI Agent
- Claude Sonnet streaming chat embedded as a panel
- Six quick-prompt buttons on empty state (pre-written financial questions)
- Optimistic UI updates, auto-scroll, disabled input during streaming
- Chat history persisted via React Query; clearable

---

## 4. UI/UX Patterns

### Terminal Aesthetic
- Monospace fonts throughout
- Amber/yellow accent for symbols, green/red for price movement
- Dark background, muted palette — feels like a real terminal

### Command Bar (the killer UX feature)
- Press `/` anywhere to open a modal command palette
- Converts input to uppercase automatically
- Supports natural ticker syntax: type "AAPL" to load a quote, "chart TSLA" to open a chart
- 9 built-in quick commands with multiple aliases (e.g., "MRKT" or "MARKET")
- Arrow up/down navigation, Enter to execute, Escape to close
- Persists recent commands in `localStorage`
- Closes automatically after execution

### Split-Pane Workspace
- Powered by `react-resizable-panels`
- Primary pane always active; secondary pane is optional
- Default split: 55% / 45%; minimums enforced (35% / 30%)
- User resize preference auto-saved via `autoSaveId`
- Each pane tracks its own view state and focused symbol independently
- Focus state determines which pane receives command bar output

### Panel System
10 named panels, each a standalone React component:
`AgentPanel`, `AlertsPanel`, `ChartPanel`, `EconomicsPanel`, `MarketOverview`, `NewsPanel`, `PortfolioPanel`, `QuotePanel`, `ScreenerPanel`, `WatchlistPanel`

Each panel has a `VIEW_META` entry that declares whether it needs a symbol (`meta.needsSymbol`). The `WorkspacePane` wrapper renders a header with pane ID, view code, symbol badge (if applicable), and FOCUS / CLOSE buttons.

### Terminal Chrome
- `TopBar` — shows active symbol and view, navigation
- `TickerTape` — scrolling price strip at the top
- `Sidebar` — quick navigation links
- `FunctionBar` — footer with F-key shortcuts (Bloomberg-style)

---

## 5. Architecture Highlights

### Caching Strategy (server-side in-memory Maps)
| Cache | TTL |
|---|---|
| Quote | 60 seconds |
| OHLCV history | 10 minutes |
| News | 5 minutes |
| Article content | 15 minutes |

No Redis or external cache — pure in-memory Maps with TTL stamps. Works fine for single-instance local use.

### Graceful Degradation Pattern
This is very well done:
1. Yahoo Finance fails → falls back to Stooq → falls back to hardcoded `PROFILE_CATALOG` reference prices
2. No API key → features are disabled with clear fallback messaging, not a crash
3. No PostgreSQL → everything works using in-memory storage (watchlist, alerts, chat history all functional)
4. News uses `Promise.allSettled()` so one dead feed doesn't break the rest

### Alerts Engine
- `alertsEngine.ts` evaluates above/below conditions against live quote prices
- `alertMonitor.ts` runs the polling loop separately
- Triggered alerts are marked to avoid duplicate notifications
- Checks are done server-side so the browser doesn't need to stay open

### Streaming AI Responses
- `POST /api/chat` streams Claude responses
- Frontend reads the response body as a stream with `TextDecoder`
- Parses `"data: {...}"` SSE lines and accumulates text fragments into state
- Same SSE streaming pattern StockPro already uses for research generation

### Single-Page, Single-Route Architecture
- Only two pages: `Terminal.tsx` and `not-found.tsx`
- Entire app lives in `Terminal.tsx` — all panels are rendered/hidden within it
- No page navigation, no URL per view — the command bar IS the navigation

---

## 6. What StockPro Could Borrow

### High-Priority Ideas

**Command Bar (`/` shortcut)**
The single highest-value UX lift. A command palette that accepts ticker symbols and view names would replace StockPro's current "search and navigate" pattern with a keyboard-first flow. Implementation is ~1 component with localStorage for history.

**Graceful Degradation in Data Providers**
BLMTRM's Yahoo → Stooq → catalog fallback chain is clean. StockPro already does Nimble → Alpha Vantage, but the same multi-provider pattern applied to price data (currently only two levels) could improve reliability.

**Quick-Prompt Buttons in AI Chat**
The 6 pre-written financial questions on the empty AI chat state are a dead-simple onboarding pattern. StockPro's research chat could benefit from the same thing — users often don't know what to ask.

**WorkspacePane Header Pattern**
Each panel showing its own ID, view code, and a symbol badge is a clean way to surface context without cluttering the content area. StockPro's report page has no such header metadata.

**RSI + SMA Overlays on Charts**
StockPro has no charting today. If charts are added, BLMTRM shows a clean way to implement SMA20/SMA50/RSI14 as toggleable overlays using Recharts.

**Peer Comparison Inside Quote View**
Showing up to 6 competitors with prices and daily changes directly on the quote panel is a low-effort, high-value feature for StockPro's research reports.

### Medium-Priority Ideas

**VIEW_META pattern**
Declaring panel metadata (does this view need a symbol? what's its code and label?) in a single config object keeps the workspace generic. Useful if StockPro's report/chat views grow.

**`autoSaveId` on layout**
`react-resizable-panels` persistence is one attribute. If StockPro adds a split-pane layout (report + chat side-by-side), this is worth knowing.

**Server-side alert monitoring**
StockPro has price alert data in the DB but no backend polling loop. BLMTRM's `alertMonitor.ts` pattern (poll prices, evaluate conditions, mark triggered) is the right approach for a future alerts feature.

---

## 7. What BLMTRM Does Not Have (StockPro Advantages)

- No multi-agent AI research pipeline — their AI is a single Claude chat, not a planner + specialized agents + synthesis
- No deep fundamental research (earnings, revenue breakdown, management quality, etc.)
- No user authentication or multi-user support
- No report storage, chunking, or vector search for follow-up Q&A
- No portfolio cost-basis tracking with CSV import
- No LangSmith / LangFuse tracing
- Pure frontend-first — real-time data only, no long-running research jobs

---

## References
- https://github.com/thompson0012/blmtrm
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/README.md
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/server/routes.ts
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/server/marketData.ts
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/server/alertsEngine.ts
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/client/src/App.tsx
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/client/src/pages/Terminal.tsx
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/client/src/components/terminal/CommandBar.tsx
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/client/src/components/panels/AgentPanel.tsx
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/client/src/components/panels/QuotePanel.tsx
- https://raw.githubusercontent.com/thompson0012/blmtrm/main/src/client/src/components/panels/ChartPanel.tsx

---
Research complete.
