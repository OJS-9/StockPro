"""
Research subject definitions for specialized agent research.
"""

from typing import Dict, List
from dataclasses import dataclass, field


@dataclass
class ResearchSubject:
    """Represents a research subject for specialized agent research."""

    id: str
    name: str
    description: str
    prompt_template: str
    trade_types: List[str] = field(default_factory=list)  # eligible trade types
    priority: Dict[str, int] = field(
        default_factory=dict
    )  # trade_type → 1=high, 2=medium, 3=low


# ─── Subject Definitions ─────────────────────────────────────────────────────

COMPANY_OVERVIEW = ResearchSubject(
    id="company_overview",
    name="Company Overview",
    description="Business model, sector, recent corporate developments, and market position",
    prompt_template="""Research and provide a structured company overview for {ticker}.

**Business model:**
- How does the company make money? (revenue model: subscription, transactional, licensing, services)
- Who are the customers? (SMB, enterprise, consumer, government — and typical contract size)
- What is the core value proposition in one sentence?

**Economic engine:**
- Primary revenue driver (volume, price, or mix)
- Gross margin profile and what drives it
- Reinvestment model: does the company grow by adding capacity, people, or technology?

**Corporate structure:**
- Key business segments and their relative size
- Recent M&A, divestitures, or strategic pivots (last 18 months)
- Any upcoming strategic decisions (CEO transition, spin-off, etc.)

**Market position:**
- Market share estimate and rank in primary market
- TAM estimate and penetration rate

Use Alpha Vantage overview tool for fundamentals. Use Perplexity for recent corporate developments and market positioning.
Quantify every claim. No valuation multiples.""",
    trade_types=["Day Trade", "Swing Trade", "Investment"],
    priority={"Day Trade": 1, "Swing Trade": 1, "Investment": 1},
)

NEWS_CATALYSTS = ResearchSubject(
    id="news_catalysts",
    name="News & Catalysts",
    description="Recent news, upcoming events, and near-term catalysts that could move the stock",
    prompt_template="""Research recent news and near-term catalysts for {ticker}.

For each catalyst, provide: **Event | Date/Timeline | Bull case impact | Bear case impact | Probability assessment**

**Near-term catalysts (0–30 days):**
- Earnings date and key metrics to watch (revenue, margins, guidance)
- Product launches or conference presentations
- Regulatory decisions pending

**Medium-term catalysts (1–3 months):**
- Analyst day, investor day, or capital markets day
- Contract wins, partnership announcements
- Macro events affecting the sector

**Sentiment data:**
- News sentiment trend (bullish / neutral / bearish) from last 30 days
- Analyst rating changes and price target revisions (last 60 days)
- Insider buying or selling (last 90 days) — net buyer or seller?

**Risks to the catalyst thesis:**
- What would make each catalyst disappoint?
- Any events that could be negative surprises?

Use Alpha Vantage news sentiment tool. Use Perplexity for real-time event calendar and analyst activity.
Quantify every claim.""",
    trade_types=["Day Trade", "Swing Trade", "Investment"],
    priority={"Day Trade": 1, "Swing Trade": 1, "Investment": 2},
)

TECHNICAL_PRICE_ACTION = ResearchSubject(
    id="technical_price_action",
    name="Technical / Price Action",
    description="Price trends, key support/resistance, volume, and momentum indicators",
    prompt_template="""Research technical price action and momentum for {ticker}.

**Price structure:**
- Trend: above/below 20, 50, 200 DMA? (state exact values if available)
- Key support levels (last 2–3 significant lows with price levels)
- Key resistance levels (last 2–3 significant highs with price levels)
- Distance from 52-week high and low (% from each)

**Volume analysis:**
- Average daily volume (20-day) vs. recent sessions
- Unusual volume spikes: date, direction, follow-through
- Accumulation vs. distribution pattern (up days vs. down days by volume)

**Momentum:**
- Relative strength vs. S&P 500 (last 30 days, quantify the delta)
- Relative strength vs. sector ETF
- Short interest: % float, days-to-cover, recent change direction

**Actionable context for trade type:**
- Day Trade: intraday range, pre-market catalyst, key levels for entry/stop
- Swing Trade: breakout/breakdown levels, catalyst timeline, risk/reward setup

Use Alpha Vantage price data. Use Perplexity for technical analysis commentary and short interest data.
State all price levels explicitly.""",
    trade_types=["Day Trade", "Swing Trade"],
    priority={"Day Trade": 1, "Swing Trade": 2},
)

EARNINGS_FINANCIALS = ResearchSubject(
    id="earnings_financials",
    name="Earnings & Financials",
    description="Recent earnings results, guidance, and key financial statement metrics",
    prompt_template="""Research earnings quality and financial health for {ticker}.

**Earnings quality:**
- Last 4–6 quarters: revenue, gross profit, operating income, EPS — actual vs. consensus
- Beat/miss cadence: consistent beater, in-liner, or miss pattern?
- Quality of beat: was it revenue-driven or cost-cuts / tax / buybacks?

**Guidance credibility:**
- Compare last 4 quarters of initial guidance vs. actual results
- Is management conservative, accurate, or aspirational in guidance?
- Current quarter and full-year guidance vs. consensus

**Cash flow quality:**
- FCF vs. net income gap (working capital dynamics, stock-based comp)
- CapEx intensity trend and maintenance vs. growth CapEx split
- Cash conversion cycle trend

**Balance sheet health:**
- Net debt / EBITDA and trend
- Current ratio, quick ratio
- Any covenant risks or refinancing needs in next 18 months

Use Alpha Vantage income statement, earnings, cash flow, and balance sheet tools.
Quantify every claim. Show trends, not snapshots.""",
    trade_types=["Swing Trade", "Investment"],
    priority={"Swing Trade": 1, "Investment": 1},
)

SECTOR_MACRO = ResearchSubject(
    id="sector_macro",
    name="Sector & Macro Context",
    description="Industry trends, macro tailwinds/headwinds, and sector rotation dynamics",
    prompt_template="""Research sector and macro context relevant to {ticker}.

**Sector context:**
- Sector ETF performance last 30/90 days vs. S&P 500 (quantify the delta)
- Where are we in the sector cycle? (early, mid, late expansion / contraction)
- Key macro variables driving the sector (rates, consumer spending, enterprise budgets, commodities)

**Sensitivity mapping:**
- If [key macro variable] moves X%, what is the historical revenue/margin impact for this sector?
- What is the beta of the sector ETF to the broader market?

**Rotation dynamics:**
- Is money flowing into or out of this sector? (fund flows, RSI of sector ETF)
- Is this a defensive or cyclical sector? Current market preference?

**Peer sector performance:**
- Name 2–3 sector peers, their YTD performance, and any recent divergence from the subject company

Use Perplexity for sector analysis and macro commentary.
Quantify all sensitivities and performance figures where possible.""",
    trade_types=["Day Trade", "Swing Trade"],
    priority={"Day Trade": 2, "Swing Trade": 2},
)

REVENUE_BREAKDOWN = ResearchSubject(
    id="revenue_breakdown",
    name="Revenue Breakdown",
    description="Revenue by segment, geography, and channel with growth trends",
    prompt_template="""Research and provide detailed revenue decomposition for {ticker}.

**Decompose revenue into: Segment × Geography × Channel × Customer type**

For each dimension:
- % contribution to total revenue
- YoY growth rate
- Margin profile if disclosed (higher-margin mix shift = positive signal)

**Attribution:**
- How much of YoY revenue growth came from: volume, price, mix, new products, M&A?
- Is mix shifting toward higher- or lower-margin segments?

**Recurring vs. non-recurring:**
- Subscription / recurring revenue as % of total
- Transactional / one-time revenue trends
- Renewal rates or re-order rates if disclosed

**Key concentration risks:**
- Top 3 customers as % of revenue
- Top 3 geographies as % of revenue

Use Alpha Vantage income statement tools. Use Perplexity for detailed segment reporting from 10-K/10-Q filings.
Quantify every claim. Show 2–4 quarter trend for each major segment.""",
    trade_types=["Swing Trade", "Investment"],
    priority={"Swing Trade": 2, "Investment": 1},
)

GROWTH_DRIVERS = ResearchSubject(
    id="growth_drivers",
    name="Growth Drivers",
    description="Key organic and inorganic growth drivers over the next 1-3 years",
    prompt_template="""Research the primary growth drivers for {ticker} using a decomposition framework.

**Growth = Volume × Price × Mix × New Products × Geography**

For each lever:
- What is the current contribution? (quantify if disclosed)
- What is the trajectory (accelerating / decelerating / inflecting)?
- What management actions or external factors drive it?

**TAM and market penetration:**
- TAM estimate and current penetration rate
- Customer count, cohort retention, and expansion revenue trends
- Product pipeline with expected revenue contribution
- Geographic white space and go-to-market model

**Sector-specific KPIs (use whichever apply):**
- SaaS: NRR, GRR, logo retention, seats/ARR per account
- Payments: TPV growth, take rate trend, new verticals
- Consumer: same-store sales, basket size, traffic vs. conversion
- Industrial: volume/price/mix split from earnings calls

Use filings and earnings transcripts. Show mechanisms, not conclusions.
No valuation multiples. Quantify every claim.""",
    trade_types=["Swing Trade", "Investment"],
    priority={"Swing Trade": 2, "Investment": 1},
)

VALUATION = ResearchSubject(
    id="valuation",
    name="Valuation & Peers",
    description="Current valuation multiples vs. peers and historical ranges",
    prompt_template="""Research the valuation and peer comparison for {ticker}.

**Current multiples:**
- P/E, P/S, EV/Revenue, EV/EBITDA, P/FCF — current vs. 1-year and 3-year historical average
- NTM vs. LTM multiples to show forward-looking premium/discount

**Peer table (3–5 direct comps):**
| Peer | P/S | EV/EBITDA | Rev Growth | Gross Margin | Premium/Discount to subject |

**Valuation rationale:**
- Is the premium/discount justified by growth rate, margin profile, or moat quality?
- At what growth rate does the current multiple imply fair value?

**Analyst consensus:**
- Price target range (low / consensus / high)
- Bull/base/bear scenarios with key assumptions

Do not provide a buy/sell recommendation — present the data and implied math.
Use Alpha Vantage financial data. Use Perplexity for peer multiples and analyst targets.""",
    trade_types=["Investment"],
    priority={"Investment": 1},
)

MARGIN_STRUCTURE = ResearchSubject(
    id="margin_structure",
    name="Margin Structure",
    description="Gross, operating, and net margin trends with segment-level profitability",
    prompt_template="""Research {ticker}'s margin structure using a margin tree framework.

**Margin Tree: Gross → Operating → EBITDA → Free Cash Flow**
For each layer: show the lever (what moves it), the trend (last 6–8 quarters), and the sensitivity.

**Unit economics:**
- Revenue per unit / ASP, COGS per unit, gross margin per unit
- Variable vs. fixed cost split (operating leverage ratio)
- For SaaS: CAC, payback period, LTV/CAC, churn-adjusted payback
- For retail/consumer: contribution margin per transaction

**Sensitivity analysis:**
- If gross margin moves ±100bps, what is the operating margin impact?
- If volume falls 10%, what is the FCF impact (given fixed cost base)?

**Operating leverage:**
- At what revenue level does the company hit positive FCF / operating leverage inflection?
- What % of OpEx is fixed vs. variable?

**Sector-specific (use whichever apply):**
- SaaS: S&M as % of new ARR, R&D as % of revenue vs. peers
- Payments: processing cost as % of TPV, interchange economics
- Industrial: capacity utilization rate, breakeven volume

Use Alpha Vantage income statement and cash flow tools.
No valuation multiples. Quantify every claim.""",
    trade_types=["Swing Trade", "Investment"],
    priority={"Swing Trade": 3, "Investment": 2},
)

COMPETITIVE_POSITION = ResearchSubject(
    id="competitive_position",
    name="Competitive Position",
    description="Competitive moat, market share, and positioning vs. key rivals",
    prompt_template="""Research {ticker}'s competitive position using a structured moat framework.

**Moat inventory — for each moat type, state whether it exists and cite evidence:**
1. Switching costs: what does it cost a customer to leave? (time, data migration, retraining)
2. Network effects: does the product get more valuable with more users?
3. Cost advantage: scale economics, proprietary supply, or process advantages
4. Intangibles: patents, licenses, brand (pricing power evidence)
5. Efficient scale: natural monopoly or oligopoly dynamics

**Competitive dynamics:**
- Top 3 competitors: name, their moat, market share estimate, key differentiator
- Win/loss dynamics: where is the company winning and losing deals, and why?
- Pricing power: has ASP / take rate held, expanded, or eroded over 3 years?
- New entrant risk: barriers to entry and any credible threats

**Customer evidence:**
- NPS or satisfaction scores if public
- Churn rate trend (quantify)
- Case studies or public customer testimonials showing stickiness

No valuation multiples. Focus on structural advantages and durability.
Use Alpha Vantage overview tool. Use Perplexity for competitive landscape analysis and market share data.""",
    trade_types=["Investment"],
    priority={"Investment": 1},
)

RISK_FACTORS = ResearchSubject(
    id="risk_factors",
    name="Risk Factors",
    description="Key risks: operational, financial, regulatory, and macro",
    prompt_template="""Research the key risk factors for {ticker}.

**For each risk, provide: Description | Probability (H/M/L) | Revenue impact if realized | Mitigants**

**Tier 1 — Existential / high-impact:**
- Regulatory or legal risk (active litigation, pending regulation)
- Customer concentration (lose top customer = X% revenue loss)
- Technology disruption risk

**Tier 2 — Operational:**
- Execution risk on key growth initiative
- Supply chain or input cost exposure
- Key-person dependency

**Tier 3 — Financial:**
- Leverage and refinancing risk
- FCF breakeven timeline if growth slows
- Dilution risk (equity raises, SBC trajectory)

**Macro sensitivities:**
- Revenue sensitivity to: interest rates, FX, consumer spending, enterprise IT budgets
- Quantify where disclosed (e.g., "10% USD strengthening → 3% revenue headwind")

Source: 10-K risk factors, recent earnings call commentary, analyst notes.
Use Alpha Vantage financials for financial risk indicators. Use Perplexity for regulatory and governance risk.""",
    trade_types=["Swing Trade", "Investment"],
    priority={"Swing Trade": 3, "Investment": 2},
)

MANAGEMENT_QUALITY = ResearchSubject(
    id="management_quality",
    name="Management Quality",
    description="Leadership track record, capital allocation discipline, and insider alignment",
    prompt_template="""Research {ticker}'s management team quality and capital allocation track record.

**Track record (last 3–5 years):**
- Revenue and EPS CAGR vs. initial guidance (how accurate was management?)
- Margins: promised vs. delivered
- Capital allocation: buybacks (EPS accretive?), M&A (value-creating?), dividends vs. reinvestment

**Capital allocation scorecard:**
- ROIC trend (is the company earning above its cost of capital?)
- FCF conversion rate (% of net income converted to FCF)
- SBC as % of revenue (dilution burden)
- M&A track record: acquisitions announced, integration outcomes, multiple paid vs. current trading multiple of target

**Alignment:**
- CEO/CFO tenure and prior track record
- Insider ownership %: executive team, board
- Insider transactions last 12 months: net buyer or seller?
- Compensation structure: short-term vs. long-term, metrics tied to comp

**Governance flags:**
- Any restatements, SEC inquiries, or material weaknesses
- Board independence %

Use Alpha Vantage financials for ROIC and FCF data. Use Perplexity for proxy filings, insider data, and governance analysis.
Quantify every claim.""",
    trade_types=["Investment"],
    priority={"Investment": 2},
)


# ─── Master List ─────────────────────────────────────────────────────────────

ALL_SUBJECTS: List[ResearchSubject] = [
    COMPANY_OVERVIEW,
    NEWS_CATALYSTS,
    TECHNICAL_PRICE_ACTION,
    EARNINGS_FINANCIALS,
    SECTOR_MACRO,
    REVENUE_BREAKDOWN,
    GROWTH_DRIVERS,
    VALUATION,
    MARGIN_STRUCTURE,
    COMPETITIVE_POSITION,
    RISK_FACTORS,
    MANAGEMENT_QUALITY,
]

_SUBJECT_MAP: Dict[str, ResearchSubject] = {s.id: s for s in ALL_SUBJECTS}


# ─── Public API ──────────────────────────────────────────────────────────────


def get_research_subjects_for_trade_type(trade_type: str) -> List[ResearchSubject]:
    """
    Return subjects eligible for the given trade type, sorted by priority (ascending).

    Args:
        trade_type: One of "Day Trade", "Swing Trade", "Investment"

    Returns:
        Priority-sorted list of ResearchSubject objects
    """
    eligible = [s for s in ALL_SUBJECTS if trade_type in s.trade_types]
    return sorted(eligible, key=lambda s: s.priority.get(trade_type, 99))


def get_research_subject_by_id(subject_id: str) -> ResearchSubject:
    """
    Get a research subject by ID.

    Args:
        subject_id: Subject ID string

    Returns:
        ResearchSubject object

    Raises:
        ValueError: If subject ID not found
    """
    subject = _SUBJECT_MAP.get(subject_id)
    if subject is None:
        raise ValueError(f"Research subject not found: {subject_id}")
    return subject


def get_research_subjects() -> List[ResearchSubject]:
    """
    Deprecated alias — returns Investment-level subjects for backwards compatibility.
    Prefer get_research_subjects_for_trade_type() for new code.
    """
    return get_research_subjects_for_trade_type("Investment")
