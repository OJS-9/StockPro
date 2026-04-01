# StockPro — Grand Slam Offer Workshop
Generated: 2026-03-30
Status: Phase 5 of 5 complete — FINAL

## Phase 0: Discovery
- Business: StockPro — AI-powered web app that consolidates the entire retail investor workflow: portfolio tracking, AI-driven company research (agentic multi-researcher), price alerts/watchlist, and news — all in one place.
- Market: Wealth. Niche: Self-directed retail investors (ages 28-42) who actively manage their own stock/crypto portfolios using scattered tools (spreadsheets, multiple apps, notes) and lack a unified, intelligent research + tracking system.
- Personas:
  - Marcus, 34 — "The Overwhelmed Analyst": Engineer, $45K portfolio, drowning in 3 spreadsheets and 2-3 hour research sessions per stock.
  - Diana, 41 — "The Serious Hobbyist": Marketing manager, $120K portfolio, 30-ticker watchlist she's barely researched, premium buyer.
  - Jordan, 28 — "The Active Trader Going Deeper": Sales rep, $18K portfolio, currently trading on vibes and Reddit — wants to be smarter.

## Phase 1: Starving Crowd
- Market scores (corrected after adversarial review): Pain 7/10, Purchasing Power 8/10, Targeting 6/10, Growth 8/10 = 29/40 — GREEN
- Core market: Wealth
- Niche (sharpened): Serious self-directed investors who manage a concentrated portfolio (8–20 positions), do their own research before buying, and trade around catalysts and earnings events. Not passive investors. Not pure day traders.
- Primary personas: Marcus (Overwhelmed Analyst) + Diana (Serious Hobbyist) — refined. Jordan is a secondary/upgrade persona.
- Pain reframe (critical fix from review): Not "consolidate your tools" — "stop making trades you haven't properly researched."
- Key moat insight: The AI pipeline is not the moat. Accumulated portfolio history, research history, and investment theses are. Every product decision must increase switching cost.
- Agent consensus: Market is real and confirmed (all 3 personas rated pain 8/10). Positioning needs to shift from workflow consolidation → investment performance outcomes. Niche accepted: concentrated + catalyst-driven investors.
- Adversarial scores: Marketer 5/10 (market selection), Strategist 6/10 (economics). Both passed with requirement to sharpen niche — done.

## Phase 2: Pricing
- Price: $29/month (Pro) · $49/month (Premium)
- Annual: $278/yr (Pro) · $399/yr (Premium) — 20% discount, cash timing play
- Position: High-Value Leader
- No freemium. 14-day free trial, no credit card required.
- Usage caps: 10 reports/mo (Pro), 30 reports/mo (Premium). Soft upsell at 80% cap.
- 10x insight: At $49/mo, one avoided bad trade on a $10K position pays for 2+ years of subscription. ROI framing replaces price comparison.
- Agent consensus: $20 = commodity trap (LTV:CAC 2.2x, unprofitable for paid acquisition). $29 clears 3x minimum. $49 tier exists to serve Diana-type premium buyers and anchor $29 as rational. All agents aligned.

## Phase 3: Value Equation
- Dream Outcome: 8/10 — "Know everything you need to know about any stock before you buy — in under 5 minutes — so you never again make a position decision based on incomplete research."
  - DO-4 (implemented): Research calibrated to trade type (Day/Swing/Investment) — AI adjusts depth and focus
  - DO-1 (planned, passive version): Attach investment thesis at buy, surface it on significant price moves. Skip LLM re-evaluation for now.
- Perceived Likelihood: 7/10 — Bridge strategy: static pre-generated sample report on landing page (not a live tool) + backtested case studies ("what StockPro would have flagged before the drop") + structured beta user outcome stories
- Time Delay: 8/10
  - TD-1 (implemented): First report typically under 3 minutes from signup. No setup required.
  - TD-4 (implemented): CSV portfolio import from any brokerage in 60 seconds. NOTE: Fidelity/Schwab/Webull silent-skip bug to fix before launch — surface skipped_count in UI.
- Effort & Sacrifice: 7/10
  - EF-2: "One StockPro report consolidates what used to take 5 tabs and 45 minutes." (Changed "replaces" → "consolidates" — more defensible)
- Agent consensus: Perceived Likelihood was the fatal gap (Marketer 2/10 without proof layer). Fixed via static proof, not live ungated tool. CSV silent-skip fix is launch-blocking. Charting is a hard zero — do not claim TradingView replacement. "Under 5 minutes" qualified to "typically under 3 minutes for most reports."

## Phase 4: Offer Stack
- Core (Pro $29/mo · Premium $49/mo):
  - Position-aware AI research reports (calibrated to Day/Swing/Investment trade type, contextualized to user's cost basis and position size)
  - Portfolio tracker (stocks + crypto) — the data layer that enables personalization
  - Watchlist + contextual price alerts (reference the research, not just price thresholds)
  - Filtered news (holdings + watchlist tickers only)
  - CSV import from any brokerage
- Bonus 1 — "The Pre-Earnings Alert": 48 hours before any held position reports earnings, email + in-app popup prompts user to generate a pre-earnings brief. Not automatic — user-initiated on trigger. Closes the "I forgot earnings were this week" gap. Primary retention engine.
- Bonus 2 — "Investment Thesis Vault": Attach thesis at buy. When significant events hit (price moves, news, earnings), StockPro evaluates whether the thesis still holds and surfaces it directly: "The margin expansion thesis you recorded may no longer hold." V1: passive version only (store + display on event; no LLM re-evaluation trigger).
- Bonus 3 — "Research History Library": All generated reports saved, searchable, attached to positions. Semantic search over own research history. Increases switching cost with every report generated.
- Positioning reframe (Phase 4 key insight): StockPro knows the user's cost basis, position size, and portfolio weight. No competitor (Seeking Alpha, Bloomberg, ChatGPT) can claim this. Every element of the stack ladders to "position-specific intelligence" — research and alerts calibrated to YOUR position, not the ticker in the abstract.
- Agent consensus: Position-aware framing is the category-of-one claim. Pre-Earnings Alert is the #1 retention mechanism. Thesis Vault closes the research-to-decision loop. Research History is the compounding switching cost.

## Phase 5: Enhancement
- Scarcity: 2-week open beta, full Pro access free. Real deadline. Authentic "reason why" — early users carry product risk and help shape the roadmap.
- Urgency: None — organic/word-of-mouth launch. Beta window is the natural event.
- Bonus stack value anchoring:
  - Pre-Earnings Alert: $19/mo comparable (Earnings Whispers Premium)
  - Investment Thesis Vault: $15/mo comparable (no direct equivalent — time-cost anchor)
  - Research History Library: $25/mo comparable (Seeking Alpha portfolio + search)
  - Total stated value: $88/mo | Your price: $29/mo (3:1 ratio)
- Guarantee Name: The 3-Report Promise
- Guarantee Type: Conditional (soft — 3 reports in 14 days proves genuine engagement, filters drive-bys)
- Guarantee Terms: "Generate 3 reports in your first 14 days. If StockPro isn't worth $29/month — tell us. Full refund, same day. No forms, no questions, no friction."
- Guarantee Category: Always-on (lives on pricing page permanently)
- Target Fear: "I'll sign up and abandon it like every other tool" — past tool abandonment is the #1 objection for both primary personas
- Name: The Active Investor's Intelligence Platform (MAGIC formula: Active=Magnet, Investor=Avatar, Intelligence=Goal, [ongoing]=Interval, Platform=Container)
- Phase 5 adversarial notes: "Pre-Trade" name rejected — contradicts the hold-cycle features (Thesis Vault, Earnings Alerts). "System" rejected — reads as infrastructure/course. "Platform" accepted. Guarantee split verdict: Marketer wanted quality-focused framing; Marcus (primary persona) validated the 3-Report Promise exactly as written. Kept as written with "full refund, same day" tightening.

## Agent Scores
- Marketer: 6.5/10 (name misfire + guarantee quality flag; both addressed)
- Strategist: 6/10 (operationally sound at current scale; silent failure states are pre-scale product risk)
- Marcus (primary persona): 8/10 to convert after beta
- Overall: 7/10 — offer is differentiated and the stack is real. Execution risk is proof layer + activation flow.

## Elevator Pitch
StockPro is the first research platform that knows your positions. While every other tool gives you generic analysis on a ticker, StockPro delivers reports calibrated to your cost basis, your position size, and your trade type — so you know exactly what a move means for your portfolio, not just the stock. Research any company in under 5 minutes, get alerted 48 hours before every earnings event on positions you hold, and build a research history that grows smarter with every trade. $29/month. 2-week free beta. No credit card required.

## Next Steps
- [ ] Fix CSV silent-skip bug — surface skipped_count in UI (Fidelity/Schwab/Webull). Launch-blocking.
- [ ] Build proof layer: static pre-generated sample report on landing page + 3 backtested case studies ("what StockPro would have flagged before the drop")
- [ ] Build Thesis Vault V1 (passive): store thesis at buy, surface on significant price events — no LLM re-evaluation
- [ ] Enforce report cap on alert-triggered reports (Pre-Earnings Alert must count against monthly quota)
- [ ] Add retry + credit restoration path for failed report generation (before 500 users)
- [ ] Fix session TTL eviction in agent_sessions dict (memory leak)
- [ ] Build beta → paid conversion email sequence (day 10 trigger: "your beta ends in 4 days — here's what you'll lose")
- [ ] Build landing page with MAGIC-named offer headline
- [ ] Create lead magnet (→ $100M Leads workshop)
- [ ] Write sales script / paid conversion page
