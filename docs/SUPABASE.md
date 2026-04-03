# Supabase (PostgreSQL) and StockPro

## How the app connects

StockPro uses **PostgreSQL** via `psycopg2` and the `DATABASE_URL` environment variable. On Supabase, use the connection string from **Project Settings → Database**:

- Prefer the **connection pooler** URI (port `6543` for transaction mode) for the Flask app to avoid exhausting database connections.
- The schema is created and migrated by `src/database.py` (`init_schema()`), not by Supabase SQL migrations in this repo.

This matches Supabase’s hosted Postgres; no MySQL-specific syntax remains in the application SQL.

## `supabase-py` client

The `supabase` package is listed in `requirements.txt` for tooling and future use (e.g. auth helpers, storage, or Edge-adjacent workflows). **Primary data access today is direct SQL through `DatabaseManager`**, not the Supabase REST client.

## Row Level Security (RLS)

Server-side code connects with a single database role from `DATABASE_URL`. **RLS policies in the Supabase dashboard apply to the PostgREST API and direct connections using roles subject to RLS.** For defense in depth:

1. Use a **least-privilege** DB user for the app if you move to Supabase’s API or pooled roles with RLS enabled.
2. Application code already scopes queries by `user_id` where applicable; add automated tests for ownership on portfolio and report mutations (see Phase 1 security items in the product roadmap).

## Local development

1. Create a Supabase project (or use local Postgres).
2. Set `DATABASE_URL` in `.env` (see `.env.example`).
3. Run the app once; `init_schema()` creates tables if missing.
