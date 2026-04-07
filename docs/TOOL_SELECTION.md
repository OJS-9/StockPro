# Tool Selection Guide

## How Tools Are Registered

Agent tools are defined in `src/langchain_tools.py` as LangChain `StructuredTool` instances, registered in priority order:

1. **yfinance** (primary): `yfinance_fundamentals`, `yfinance_analyst`, `yfinance_ownership`, `yfinance_options`
2. **MCP** (selective): only tools in `ESSENTIAL_MCP_TOOLS` -- currently just `NEWS_SENTIMENT`
3. **Nimble** (web): `nimble_web_search`, `nimble_extract`, `perplexity_research`

To change which MCP tools are active in agents, edit the `ESSENTIAL_MCP_TOOLS` set in `src/langchain_tools.py`.

## Alpha Vantage MCP Tools (6 total)

All tools are accessible via `src/mcp_tools.py` for direct use, but only NEWS_SENTIMENT is registered as an agent tool (yfinance covers the rest).

1. **OVERVIEW** -- Company profile and fundamental data
   - Parameters: `symbol` (string, required)
   - Returns: Company name, description, sector, P/E ratio, revenue, EBITDA, and other fundamentals

2. **INCOME_STATEMENT** -- Company income statement data
   - Parameters: `symbol` (string, required)
   - Returns: Revenue, expenses, net income, and other income statement metrics

3. **BALANCE_SHEET** -- Company balance sheet data
   - Parameters: `symbol` (string, required)
   - Returns: Assets, liabilities, equity, and other balance sheet items

4. **CASH_FLOW** -- Company cash flow statement data
   - Parameters: `symbol` (string, required)
   - Returns: Operating, investing, and financing cash flows

5. **EARNINGS** -- Company earnings data
   - Parameters: `symbol` (string, required)
   - Returns: Quarterly and annual earnings data

6. **NEWS_SENTIMENT** -- News articles and sentiment analysis (active in agents)
   - Parameters: `ticker` (string, required), `limit` (integer, optional, default 50)
   - Returns: Recent news articles and sentiment scores

## Rationale

yfinance provides fundamentals, analyst data, ownership, and options data without rate limits. Alpha Vantage MCP is reserved for NEWS_SENTIMENT because yfinance does not provide sentiment-scored news. This keeps token usage low while providing comprehensive research coverage.

## Truncation

Tool outputs are truncated before passing to agents:
- Financial arrays (annualReports, quarterlyReports, etc.): max 5 items
- News items: max 5 items

This is handled in `src/langchain_tools.py` via `MAX_SERIES_ITEMS` and `MAX_NEWS_ITEMS`.

## Available MCP Tools

Full catalog: https://mcp.alphavantage.co/

Categories: Time Series, Fundamentals, News, Technical Indicators, Commodities, Forex, Crypto.
