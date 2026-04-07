# Supabase (PostgreSQL) and StockPro

## How the app connects

StockPro uses **PostgreSQL** via `psycopg2` and the `DATABASE_URL` environment variable. On Supabase, use the connection string from **Project Settings -> Database**:

- Prefer the **connection pooler** URI (port `6543` for transaction mode) to avoid exhausting connections.
- Schema is created and migrated by `src/database.py` (`init_schema()`), not by Supabase SQL migrations.
- No MySQL-specific syntax remains in the application SQL.

## `supabase-py` client

The `supabase` package is in `requirements.txt` for tooling and future use. **Primary data access is direct SQL through `DatabaseManager`**, not the Supabase REST client.

## Row Level Security (RLS)

Server-side code connects with a single database role from `DATABASE_URL`. RLS policies in the Supabase dashboard apply to the PostgREST API and direct connections using roles subject to RLS.

### Patterns

- **Direct `user_id` column**: `USING (user_id = auth.jwt()->>'sub')` -- used for users, portfolios, reports, watchlists, alerts, ticker_notes
- **Join through parent**: holdings join through portfolios, report_chunks join through reports, transactions join through holdings
- **Shared read-only** (e.g. price_cache): `FOR SELECT USING (true)` -- writes only via backend/service_role
- **Sensitive tokens** (e.g. telegram_connect_tokens): same user_id pattern, optionally omit SELECT for browser

### Current user ID in SQL

```sql
auth.jwt()->>'sub'   -- Clerk user ID (e.g. user_abc123)
```

### Adding a new table

1. `ALTER TABLE public.<table_name> ENABLE ROW LEVEL SECURITY;`
2. Add appropriate policy (direct user_id, parent join, or shared read)
3. Add automated tests for ownership scoping (see `tests/test_database_ownership_scoping.py`)

## Local development

1. Create a Supabase project (or use local Postgres).
2. Set `DATABASE_URL` in `.env` (see `.env.example`).
3. Run the app once; `init_schema()` creates tables if missing.
