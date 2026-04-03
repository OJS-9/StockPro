"""
PostgreSQL database connection and schema management for reports, chunks, and portfolios.
"""

import logging
import os
import threading
import json
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import psycopg2
import psycopg2.pool
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL database connections and operations for reports and chunks."""

    def __init__(self):
        """Initialize database manager with connection pool."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                1,
                5,
                dsn=database_url,
                connect_timeout=10,
                options="-c statement_timeout=30000",
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )
            logger.info("PostgreSQL connection pool initialized")
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to create PostgreSQL connection pool: {e}")

    def get_connection(self):
        """Get a connection from the pool, validating it is alive."""
        try:
            conn = self._pool.getconn()
            # Check if connection is still alive; discard stale ones
            if conn.closed:
                self._pool.putconn(conn, close=True)
                conn = self._pool.getconn()
            return conn
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get connection from pool: {e}")

    def _release(self, conn):
        """Return a connection to the pool."""
        if conn is not None:
            try:
                self._pool.putconn(conn)
            except Exception:
                pass

    def init_schema(self):
        """Initialize database schema (create tables if they don't exist)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:

                # Trigger function for updated_at auto-update
                cur.execute("""
                    CREATE OR REPLACE FUNCTION update_updated_at()
                    RETURNS TRIGGER AS $$
                    BEGIN
                      NEW.updated_at = NOW();
                      RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql
                """)

                # Users
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id       VARCHAR(36)  PRIMARY KEY,
                        username      VARCHAR(80)  NOT NULL UNIQUE,
                        email         VARCHAR(120) NOT NULL UNIQUE,
                        password_hash VARCHAR(255),
                        google_id     VARCHAR(255) UNIQUE,
                        tier          VARCHAR(20)  NOT NULL DEFAULT 'free',
                        is_pro        BOOLEAN      NOT NULL DEFAULT FALSE,
                        telegram_chat_id VARCHAR(64),
                        created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'is_pro'
                        ) THEN
                            ALTER TABLE users ADD COLUMN is_pro BOOLEAN NOT NULL DEFAULT FALSE;
                        END IF;
                    END $$
                """)
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'telegram_chat_id'
                        ) THEN
                            ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(64);
                        END IF;
                    END $$
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_username  ON users (username)"
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_email     ON users (email)")
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_google_id ON users (google_id)"
                )

                # Telegram connect tokens (one-time link codes)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_connect_tokens (
                        token       VARCHAR(64) PRIMARY KEY,
                        user_id     VARCHAR(36) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        expires_at  TIMESTAMP   NOT NULL,
                        created_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_telegram_connect_user_id ON telegram_connect_tokens (user_id)"
                )

                # Reports
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reports (
                        report_id   VARCHAR(36) PRIMARY KEY,
                        user_id     VARCHAR(36) REFERENCES users(user_id) ON DELETE SET NULL,
                        ticker      VARCHAR(10) NOT NULL,
                        trade_type  VARCHAR(50) NOT NULL,
                        report_text TEXT        NOT NULL,
                        metadata    JSONB,
                        created_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_report_ticker     ON reports (ticker)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_report_created_at ON reports (created_at)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_report_user_id    ON reports (user_id)"
                )

                # Report chunks
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS report_chunks (
                        chunk_id    VARCHAR(36) PRIMARY KEY,
                        report_id   VARCHAR(36) NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
                        chunk_text  TEXT        NOT NULL,
                        section     VARCHAR(500),
                        chunk_index INT         NOT NULL,
                        embedding   JSONB,
                        chunk_type  VARCHAR(20) DEFAULT 'report',
                        created_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunk_report_id ON report_chunks (report_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunk_section   ON report_chunks (section)"
                )
                # Idempotent migration for existing databases
                cur.execute(
                    "ALTER TABLE report_chunks ADD COLUMN IF NOT EXISTS chunk_type VARCHAR(20) DEFAULT 'report'"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunk_type ON report_chunks (chunk_type)"
                )

                # Portfolios
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS portfolios (
                        portfolio_id  VARCHAR(36)   PRIMARY KEY,
                        name          VARCHAR(100)  NOT NULL DEFAULT 'My Portfolio',
                        description   TEXT,
                        user_id       VARCHAR(36)   REFERENCES users(user_id) ON DELETE SET NULL,
                        track_cash    BOOLEAN       NOT NULL DEFAULT FALSE,
                        cash_balance  NUMERIC(18,2) NOT NULL DEFAULT 0,
                        created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
                        updated_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'set_portfolios_updated_at'
                        ) THEN
                            CREATE TRIGGER set_portfolios_updated_at
                            BEFORE UPDATE ON portfolios
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
                        END IF;
                    END $$
                """)

                # Holdings
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS holdings (
                        holding_id       VARCHAR(36)   PRIMARY KEY,
                        portfolio_id     VARCHAR(36)   NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
                        symbol           VARCHAR(20)   NOT NULL,
                        asset_type       VARCHAR(10)   NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
                        total_quantity   NUMERIC(18,8) NOT NULL DEFAULT 0,
                        average_cost     NUMERIC(18,8) NOT NULL DEFAULT 0,
                        total_cost_basis NUMERIC(18,2) NOT NULL DEFAULT 0,
                        created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
                        updated_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (portfolio_id, symbol)
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_id ON holdings (portfolio_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_holdings_symbol       ON holdings (symbol)"
                )
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'set_holdings_updated_at'
                        ) THEN
                            CREATE TRIGGER set_holdings_updated_at
                            BEFORE UPDATE ON holdings
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
                        END IF;
                    END $$
                """)

                # Transactions
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        transaction_id   VARCHAR(36)   PRIMARY KEY,
                        holding_id       VARCHAR(36)   NOT NULL REFERENCES holdings(holding_id) ON DELETE CASCADE,
                        transaction_type VARCHAR(10)   NOT NULL CHECK (transaction_type IN ('buy', 'sell')),
                        quantity         NUMERIC(18,8) NOT NULL,
                        price_per_unit   NUMERIC(18,8) NOT NULL,
                        fees             NUMERIC(18,2) DEFAULT 0,
                        transaction_date TIMESTAMP     NOT NULL,
                        notes            TEXT,
                        import_source    VARCHAR(50),
                        created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_txn_holding_id ON transactions (holding_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_txn_date       ON transactions (transaction_date)"
                )

                # CSV imports
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS csv_imports (
                        import_id     VARCHAR(36)  PRIMARY KEY,
                        portfolio_id  VARCHAR(36)  NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
                        filename      VARCHAR(255) NOT NULL,
                        row_count     INT          NOT NULL,
                        success_count INT          NOT NULL,
                        error_count   INT          NOT NULL,
                        errors_json   JSONB,
                        imported_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_csv_portfolio_id ON csv_imports (portfolio_id)"
                )

                # Watchlists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS watchlists (
                        watchlist_id VARCHAR(36)  PRIMARY KEY,
                        user_id      VARCHAR(36)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        name         VARCHAR(100) NOT NULL DEFAULT 'My Watchlist',
                        position     INT          NOT NULL DEFAULT 0,
                        created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                        updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists (user_id)"
                )
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'set_watchlists_updated_at'
                        ) THEN
                            CREATE TRIGGER set_watchlists_updated_at
                            BEFORE UPDATE ON watchlists
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
                        END IF;
                    END $$
                """)

                # Watchlist sections
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS watchlist_sections (
                        section_id   VARCHAR(36)  PRIMARY KEY,
                        watchlist_id VARCHAR(36)  NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
                        name         VARCHAR(100) NOT NULL,
                        position     INT          NOT NULL DEFAULT 0,
                        created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sections_watchlist_id ON watchlist_sections (watchlist_id)"
                )

                # Watchlist items
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS watchlist_items (
                        item_id      VARCHAR(36)  PRIMARY KEY,
                        watchlist_id VARCHAR(36)  NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
                        section_id   VARCHAR(36)  REFERENCES watchlist_sections(section_id) ON DELETE SET NULL,
                        symbol       VARCHAR(20)  NOT NULL,
                        asset_type   VARCHAR(10)  NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
                        display_name VARCHAR(100),
                        position     INT          NOT NULL DEFAULT 0,
                        is_pinned    BOOLEAN      NOT NULL DEFAULT FALSE,
                        created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (watchlist_id, symbol)
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_items_watchlist_id ON watchlist_items (watchlist_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_items_section_id   ON watchlist_items (section_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_items_symbol       ON watchlist_items (symbol)"
                )

                # Per-user ticker notes (rich text from /ticker/<symbol>)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ticker_notes (
                        user_id    VARCHAR(36) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        symbol     VARCHAR(20) NOT NULL,
                        content    TEXT        NOT NULL DEFAULT '',
                        created_at TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, symbol)
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ticker_notes_symbol ON ticker_notes (symbol)"
                )
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'set_ticker_notes_updated_at'
                        ) THEN
                            CREATE TRIGGER set_ticker_notes_updated_at
                            BEFORE UPDATE ON ticker_notes
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
                        END IF;
                    END $$
                """)

                # Price cache
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS price_cache (
                        symbol         VARCHAR(20)   PRIMARY KEY,
                        asset_type     VARCHAR(10)   NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
                        price          NUMERIC(18,8),
                        change_percent NUMERIC(10,4),
                        display_name   VARCHAR(100),
                        last_updated   TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_price_cache_last_updated ON price_cache (last_updated)"
                )

                # Price alerts (user-defined targets vs cached quotes; evaluation in jobs later)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS price_alerts (
                        alert_id          VARCHAR(36) PRIMARY KEY,
                        user_id           VARCHAR(36) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        symbol            VARCHAR(20) NOT NULL,
                        asset_type        VARCHAR(10) NOT NULL DEFAULT 'stock'
                            CHECK (asset_type IN ('stock', 'crypto')),
                        direction         VARCHAR(10) NOT NULL CHECK (direction IN ('above', 'below')),
                        target_price      NUMERIC(18, 8) NOT NULL,
                        active            BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_triggered_at TIMESTAMP NULL
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id ON price_alerts (user_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol ON price_alerts (symbol)"
                )
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'set_price_alerts_updated_at'
                        ) THEN
                            CREATE TRIGGER set_price_alerts_updated_at
                            BEFORE UPDATE ON price_alerts
                            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
                        END IF;
                    END $$
                """)

                # Fired when an alert condition matches cached price (in-app notification feed)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS price_alert_notifications (
                        notification_id   VARCHAR(36) PRIMARY KEY,
                        user_id           VARCHAR(36) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        alert_id          VARCHAR(36) NOT NULL REFERENCES price_alerts(alert_id) ON DELETE CASCADE,
                        symbol            VARCHAR(20) NOT NULL,
                        body              TEXT NOT NULL,
                        read_at           TIMESTAMP NULL,
                        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pan_user_created ON price_alert_notifications (user_id, created_at DESC)"
                )
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pan_user_unread
                    ON price_alert_notifications (user_id)
                    WHERE read_at IS NULL
                    """)

                # Public waitlist signups (pre-launch; no mail provider yet)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS waitlist_emails (
                        id         SERIAL PRIMARY KEY,
                        email      TEXT UNIQUE NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                """)

                # Monthly research report usage (free tier quota)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS report_usage (
                        user_id      VARCHAR(36) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        period       CHAR(7)     NOT NULL,
                        report_count INT         NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, period)
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_report_usage_period ON report_usage (period)"
                )

            conn.commit()
            logger.info("Database schema initialized")

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to initialize schema: {e}")
        finally:
            self._release(conn)

    def add_waitlist_email(self, email: str) -> None:
        """Persist a waitlist signup. Duplicate emails are ignored (idempotent)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO waitlist_emails (email)
                    VALUES (%s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (email,),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to save waitlist email: {e}") from e
        finally:
            self._release(conn)

    def save_report(
        self,
        ticker: str,
        trade_type: str,
        report_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Save a report to the database. Returns report_id."""
        report_id = str(uuid.uuid4())
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reports (report_id, user_id, ticker, trade_type, report_text, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        report_id,
                        user_id,
                        ticker.upper(),
                        trade_type,
                        report_text,
                        json.dumps(metadata) if metadata else None,
                    ),
                )
            conn.commit()
            return report_id
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to save report: {e}")
        finally:
            self._release(conn)

    def get_report(
        self, report_id: str, user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a report by ID, optionally verifying ownership."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if user_id:
                    cur.execute(
                        """
                        SELECT report_id, user_id, ticker, trade_type, report_text, metadata, created_at
                        FROM reports WHERE report_id = %s AND user_id = %s
                    """,
                        (report_id, user_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT report_id, user_id, ticker, trade_type, report_text, metadata, created_at
                        FROM reports WHERE report_id = %s
                    """,
                        (report_id,),
                    )
                return cur.fetchone()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get report: {e}")
        finally:
            self._release(conn)

    def get_reports_by_ticker(
        self, ticker: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent reports for a ticker."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT report_id, ticker, trade_type, report_text, metadata, created_at
                    FROM reports WHERE ticker = %s ORDER BY created_at DESC LIMIT %s
                """,
                    (ticker.upper(), limit),
                )
                return cur.fetchall()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get reports by ticker: {e}")
        finally:
            self._release(conn)

    def get_all_reports(
        self,
        ticker: Optional[str] = None,
        trade_type: Optional[str] = None,
        sort_order: str = "DESC",
        limit: int = 20,
        offset: int = 0,
        user_id: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Get paginated reports with optional filtering."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                where_clauses = []
                params = []

                if user_id:
                    where_clauses.append("user_id = %s")
                    params.append(user_id)
                if ticker:
                    where_clauses.append("ticker = %s")
                    params.append(ticker.upper())
                if trade_type:
                    where_clauses.append("trade_type = %s")
                    params.append(trade_type)

                where_sql = (
                    ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
                )
                sort_order = (
                    "DESC"
                    if sort_order.upper() not in ("ASC", "DESC")
                    else sort_order.upper()
                )

                cur.execute(
                    f"SELECT COUNT(*) as total FROM reports {where_sql}", params
                )
                total_count = cur.fetchone()["total"]

                cur.execute(
                    f"""
                    SELECT report_id, user_id, ticker, trade_type, report_text, metadata, created_at
                    FROM reports {where_sql}
                    ORDER BY created_at {sort_order}
                    LIMIT %s OFFSET %s
                """,
                    params + [limit, offset],
                )

                return cur.fetchall(), total_count
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get all reports: {e}")
        finally:
            self._release(conn)

    def get_report_ticker_summaries(
        self,
        *,
        user_id: str,
        ticker: Optional[str] = None,
        sort_order: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Get one row per ticker with latest report metadata and per-ticker report count.
        """
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                where_parts = ["r.user_id = %s"]
                params: List[Any] = [user_id]
                if ticker:
                    where_parts.append("r.ticker = %s")
                    params.append(ticker.upper())
                where_sql = " AND ".join(where_parts)
                sort_order = (
                    "DESC"
                    if sort_order.upper() not in ("ASC", "DESC")
                    else sort_order.upper()
                )

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM (
                        SELECT DISTINCT r.ticker
                        FROM reports r
                        WHERE {where_sql}
                    ) t
                    """,
                    params,
                )
                total_count = int(cur.fetchone()["total"])

                cur.execute(
                    f"""
                    WITH filtered AS (
                        SELECT r.*
                        FROM reports r
                        WHERE {where_sql}
                    ),
                    latest AS (
                        SELECT DISTINCT ON (ticker)
                            ticker,
                            report_id,
                            trade_type,
                            report_text,
                            created_at
                        FROM filtered
                        ORDER BY ticker, created_at DESC
                    ),
                    counts AS (
                        SELECT ticker, COUNT(*) AS report_count
                        FROM filtered
                        GROUP BY ticker
                    )
                    SELECT
                        l.ticker,
                        l.report_id,
                        l.trade_type,
                        l.report_text,
                        l.created_at,
                        c.report_count
                    FROM latest l
                    JOIN counts c ON c.ticker = l.ticker
                    ORDER BY l.created_at {sort_order}
                    LIMIT %s OFFSET %s
                    """,
                    params + [limit, offset],
                )
                return list(cur.fetchall()), total_count
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get report ticker summaries: {e}")
        finally:
            self._release(conn)

    def save_chunks(self, report_id: str, chunks: List[Dict[str, Any]]):
        """Save report chunks with embeddings."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                for chunk in chunks:
                    chunk_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO report_chunks
                        (chunk_id, report_id, chunk_text, section, chunk_index, embedding, chunk_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            chunk_id,
                            report_id,
                            chunk["chunk_text"],
                            chunk.get("section"),
                            chunk["chunk_index"],
                            (
                                json.dumps(chunk.get("embedding"))
                                if chunk.get("embedding")
                                else None
                            ),
                            chunk.get("chunk_type", "report"),
                        ),
                    )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to save chunks: {e}")
        finally:
            self._release(conn)

    def get_chunks_by_report(
        self, report_id: str, include_embeddings: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a report."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if include_embeddings:
                    cur.execute(
                        """
                        SELECT chunk_id, report_id, chunk_text, section, chunk_index, embedding, chunk_type, created_at
                        FROM report_chunks WHERE report_id = %s ORDER BY chunk_index ASC
                    """,
                        (report_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT chunk_id, report_id, chunk_text, section, chunk_index, chunk_type, created_at
                        FROM report_chunks WHERE report_id = %s ORDER BY chunk_index ASC
                    """,
                        (report_id,),
                    )
                return cur.fetchall()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get chunks: {e}")
        finally:
            self._release(conn)

    def delete_report(self, report_id: str):
        """Delete a report and all its chunks (cascade)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM reports WHERE report_id = %s", (report_id,))
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to delete report: {e}")
        finally:
            self._release(conn)

    # ==================== Portfolio Methods ====================

    def create_portfolio(
        self,
        portfolio_id: str,
        name: str = "My Portfolio",
        description: str = "",
        user_id: Optional[str] = None,
        track_cash: bool = False,
        cash_balance: float = 0.0,
    ):
        """Create a new portfolio."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO portfolios (portfolio_id, name, description, user_id, track_cash, cash_balance)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        portfolio_id,
                        name,
                        description,
                        user_id,
                        track_cash,
                        cash_balance,
                    ),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create portfolio: {e}")
        finally:
            self._release(conn)

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """Get portfolio by ID."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT portfolio_id, name, description, user_id, created_at, updated_at,
                           COALESCE(track_cash, FALSE) AS track_cash,
                           COALESCE(cash_balance, 0) AS cash_balance
                    FROM portfolios WHERE portfolio_id = %s
                """,
                    (portfolio_id,),
                )
                return cur.fetchone()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get portfolio: {e}")
        finally:
            self._release(conn)

    def update_cash_balance(self, portfolio_id: str, cash_balance: float) -> None:
        """Update the cash balance for a portfolio."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE portfolios SET cash_balance = %s WHERE portfolio_id = %s
                """,
                    (cash_balance, portfolio_id),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to update cash balance: {e}")
        finally:
            self._release(conn)

    def list_portfolios(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List portfolios, optionally filtered by user."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if user_id is not None:
                    cur.execute(
                        """
                        SELECT portfolio_id, name, description, user_id, created_at, updated_at,
                               COALESCE(track_cash, FALSE) AS track_cash,
                               COALESCE(cash_balance, 0) AS cash_balance
                        FROM portfolios WHERE user_id = %s ORDER BY created_at ASC
                    """,
                        (user_id,),
                    )
                else:
                    cur.execute("""
                        SELECT portfolio_id, name, description, user_id, created_at, updated_at,
                               COALESCE(track_cash, FALSE) AS track_cash,
                               COALESCE(cash_balance, 0) AS cash_balance
                        FROM portfolios ORDER BY created_at ASC
                    """)
                return cur.fetchall()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to list portfolios: {e}")
        finally:
            self._release(conn)

    # ==================== User Methods ====================

    def create_user(
        self,
        user_id: str,
        username: str,
        email: str,
        password_hash: Optional[str] = None,
        google_id: Optional[str] = None,
    ):
        """Create a new user."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (user_id, username, email, password_hash, google_id)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    (user_id, username, email, password_hash, google_id),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create user: {e}")
        finally:
            self._release(conn)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a user by username."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, username, email, password_hash, google_id, tier,
                           COALESCE(is_pro, FALSE) AS is_pro, telegram_chat_id, created_at
                    FROM users WHERE username = %s
                """,
                    (username,),
                )
                return cur.fetchone()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            self._release(conn)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, username, email, password_hash, google_id, tier,
                           COALESCE(is_pro, FALSE) AS is_pro, telegram_chat_id, created_at
                    FROM users WHERE user_id = %s
                """,
                    (user_id,),
                )
                return cur.fetchone()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            self._release(conn)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, username, email, password_hash, google_id, tier,
                           COALESCE(is_pro, FALSE) AS is_pro, telegram_chat_id, created_at
                    FROM users WHERE email = %s
                """,
                    (email,),
                )
                return cur.fetchone()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            self._release(conn)

    def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by Google OAuth sub (google_id)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, username, email, password_hash, google_id, tier,
                           COALESCE(is_pro, FALSE) AS is_pro, telegram_chat_id, created_at
                    FROM users WHERE google_id = %s
                """,
                    (google_id,),
                )
                return cur.fetchone()
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            self._release(conn)

    def update_user_google_id(self, user_id: str, google_id: str):
        """Link a Google account to an existing user."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users SET google_id = %s WHERE user_id = %s
                """,
                    (google_id, user_id),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to update user: {e}")
        finally:
            self._release(conn)

    def user_is_pro(self, user_id: str) -> bool:
        """Paid / pro users bypass free-tier report quota (stub until billing)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(is_pro, FALSE) FROM users WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                return bool(row and row[0])
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to read user tier: {e}")
        finally:
            self._release(conn)

    def set_user_telegram_chat_id(self, user_id: str, telegram_chat_id: str) -> None:
        """Persist Telegram chat_id on the users table."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET telegram_chat_id = %s WHERE user_id = %s",
                    (str(telegram_chat_id), user_id),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to set telegram_chat_id: {e}")
        finally:
            self._release(conn)

    def create_telegram_connect_token(self, user_id: str, ttl_minutes: int = 10) -> str:
        """Create a short-lived, one-time token for linking a Telegram chat to a user."""
        token = uuid.uuid4().hex
        expires_at = datetime.utcnow() + timedelta(minutes=int(ttl_minutes))
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telegram_connect_tokens (token, user_id, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (token, user_id, expires_at),
                )
            conn.commit()
            return token
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create telegram connect token: {e}")
        finally:
            self._release(conn)

    def consume_telegram_connect_token(
        self, token: str, telegram_chat_id: str
    ) -> Optional[str]:
        """
        Atomically validate+consume a connect token and link the chat id.

        Returns:
            user_id if token was valid; otherwise None.
        """
        token = (token or "").strip()
        if not token:
            return None
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT token, user_id, expires_at
                    FROM telegram_connect_tokens
                    WHERE token = %s
                    """,
                    (token,),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return None
                if row["expires_at"] < datetime.utcnow():
                    cur.execute(
                        "DELETE FROM telegram_connect_tokens WHERE token = %s", (token,)
                    )
                    conn.commit()
                    return None

                user_id = row["user_id"]
                cur.execute(
                    "UPDATE users SET telegram_chat_id = %s WHERE user_id = %s",
                    (str(telegram_chat_id), user_id),
                )
                cur.execute(
                    "DELETE FROM telegram_connect_tokens WHERE token = %s", (token,)
                )
            conn.commit()
            return user_id
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to consume telegram connect token: {e}")
        finally:
            self._release(conn)

    def get_report_usage_count(self, user_id: str, period: str) -> int:
        """Monthly report count for quota (period = YYYY-MM)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT report_count FROM report_usage
                    WHERE user_id = %s AND period = %s
                    """,
                    (user_id, period),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to read report usage: {e}")
        finally:
            self._release(conn)

    def increment_report_usage(
        self, user_id: str, period: Optional[str] = None
    ) -> None:
        """
        Count one successful report toward the user's monthly quota.
        No-op for pro users. Caller passes period (default: current UTC month).
        """
        if self.user_is_pro(user_id):
            return

        if period is None:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO report_usage (user_id, period, report_count)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (user_id, period) DO UPDATE SET
                        report_count = report_usage.report_count + 1
                    """,
                    (user_id, period),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to increment report usage: {e}")
        finally:
            self._release(conn)

    # ==================== Holdings Methods ====================

    def create_holding(
        self, holding_id: str, portfolio_id: str, symbol: str, asset_type: str
    ):
        """Create a new holding."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO holdings (holding_id, portfolio_id, symbol, asset_type)
                    VALUES (%s, %s, %s, %s)
                """,
                    (holding_id, portfolio_id, symbol.upper(), asset_type),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create holding: {e}")
        finally:
            self._release(conn)

    def get_holding(self, portfolio_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific holding by portfolio and symbol."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT holding_id, portfolio_id, symbol, asset_type,
                           total_quantity, average_cost, total_cost_basis,
                           created_at, updated_at
                    FROM holdings WHERE portfolio_id = %s AND symbol = %s
                """,
                    (portfolio_id, symbol.upper()),
                )
                result = cur.fetchone()
            if result:
                result["total_quantity"] = Decimal(str(result["total_quantity"]))
                result["average_cost"] = Decimal(str(result["average_cost"]))
                result["total_cost_basis"] = Decimal(str(result["total_cost_basis"]))
            return result
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get holding: {e}")
        finally:
            self._release(conn)

    def get_holding_by_id(self, holding_id: str) -> Optional[Dict[str, Any]]:
        """Get a holding by its ID."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT holding_id, portfolio_id, symbol, asset_type,
                           total_quantity, average_cost, total_cost_basis,
                           created_at, updated_at
                    FROM holdings WHERE holding_id = %s
                """,
                    (holding_id,),
                )
                result = cur.fetchone()
            if result:
                result["total_quantity"] = Decimal(str(result["total_quantity"]))
                result["average_cost"] = Decimal(str(result["average_cost"]))
                result["total_cost_basis"] = Decimal(str(result["total_cost_basis"]))
            return result
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get holding: {e}")
        finally:
            self._release(conn)

    def get_holdings(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """Get all holdings for a portfolio."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT holding_id, portfolio_id, symbol, asset_type,
                           total_quantity, average_cost, total_cost_basis,
                           created_at, updated_at
                    FROM holdings WHERE portfolio_id = %s ORDER BY symbol ASC
                """,
                    (portfolio_id,),
                )
                results = cur.fetchall()
            for result in results:
                result["total_quantity"] = Decimal(str(result["total_quantity"]))
                result["average_cost"] = Decimal(str(result["average_cost"]))
                result["total_cost_basis"] = Decimal(str(result["total_cost_basis"]))
            return results
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get holdings: {e}")
        finally:
            self._release(conn)

    def update_holding(
        self,
        holding_id: str,
        total_quantity: Decimal,
        average_cost: Decimal,
        total_cost_basis: Decimal,
    ):
        """Update holding totals."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE holdings
                    SET total_quantity = %s, average_cost = %s, total_cost_basis = %s
                    WHERE holding_id = %s
                """,
                    (
                        str(total_quantity),
                        str(average_cost),
                        str(total_cost_basis),
                        holding_id,
                    ),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to update holding: {e}")
        finally:
            self._release(conn)

    def delete_holding(self, holding_id: str):
        """Delete a holding and all its transactions (cascade)."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM holdings WHERE holding_id = %s", (holding_id,))
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to delete holding: {e}")
        finally:
            self._release(conn)

    # ==================== Transaction Methods ====================

    def add_transaction(
        self,
        transaction_id: str,
        holding_id: str,
        transaction_type: str,
        quantity: Decimal,
        price_per_unit: Decimal,
        fees: Decimal,
        transaction_date: datetime,
        notes: str = "",
        import_source: str = "manual",
    ):
        """Add a transaction to a holding."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO transactions
                    (transaction_id, holding_id, transaction_type, quantity,
                     price_per_unit, fees, transaction_date, notes, import_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        transaction_id,
                        holding_id,
                        transaction_type,
                        str(quantity),
                        str(price_per_unit),
                        str(fees),
                        transaction_date,
                        notes,
                        import_source,
                    ),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to add transaction: {e}")
        finally:
            self._release(conn)

    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get a transaction by ID."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT transaction_id, holding_id, transaction_type, quantity,
                           price_per_unit, fees, transaction_date, notes, import_source, created_at
                    FROM transactions WHERE transaction_id = %s
                """,
                    (transaction_id,),
                )
                result = cur.fetchone()
            if result:
                result["quantity"] = Decimal(str(result["quantity"]))
                result["price_per_unit"] = Decimal(str(result["price_per_unit"]))
                result["fees"] = Decimal(str(result["fees"]))
            return result
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get transaction: {e}")
        finally:
            self._release(conn)

    def get_transactions(self, holding_id: str) -> List[Dict[str, Any]]:
        """Get all transactions for a holding."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT transaction_id, holding_id, transaction_type, quantity,
                           price_per_unit, fees, transaction_date, notes, import_source, created_at
                    FROM transactions WHERE holding_id = %s ORDER BY transaction_date ASC
                """,
                    (holding_id,),
                )
                results = cur.fetchall()
            for result in results:
                result["quantity"] = Decimal(str(result["quantity"]))
                result["price_per_unit"] = Decimal(str(result["price_per_unit"]))
                result["fees"] = Decimal(str(result["fees"]))
            return results
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get transactions: {e}")
        finally:
            self._release(conn)

    def delete_transaction(self, transaction_id: str):
        """Delete a transaction."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM transactions WHERE transaction_id = %s",
                    (transaction_id,),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to delete transaction: {e}")
        finally:
            self._release(conn)

    def get_all_portfolio_transactions(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """Get all transactions for a portfolio joined with holding symbol and asset_type."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.transaction_id, t.holding_id, t.transaction_type, t.quantity,
                           t.price_per_unit, t.fees, t.transaction_date, t.notes,
                           h.symbol, h.asset_type
                    FROM transactions t
                    JOIN holdings h ON t.holding_id = h.holding_id
                    WHERE h.portfolio_id = %s
                    ORDER BY t.transaction_date ASC
                """,
                    (portfolio_id,),
                )
                results = cur.fetchall()
            for result in results:
                result["quantity"] = Decimal(str(result["quantity"]))
                result["price_per_unit"] = Decimal(str(result["price_per_unit"]))
                result["fees"] = Decimal(str(result["fees"]))
            return results
        except psycopg2.Error as e:
            raise RuntimeError(f"Failed to get portfolio transactions: {e}")
        finally:
            self._release(conn)

    # ==================== Watchlist Methods ====================

    def create_watchlist(self, watchlist_id, user_id, name="My Watchlist"):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO watchlists (watchlist_id, user_id, name) VALUES (%s, %s, %s)",
                    (watchlist_id, user_id, name),
                )
            conn.commit()
        finally:
            self._release(conn)

    def get_watchlist(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM watchlists WHERE watchlist_id = %s", (watchlist_id,)
                )
                return cur.fetchone()
        finally:
            self._release(conn)

    def list_watchlists(self, user_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM watchlists WHERE user_id = %s ORDER BY position, created_at",
                    (user_id,),
                )
                return cur.fetchall()
        finally:
            self._release(conn)

    def update_watchlist(self, watchlist_id, name):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE watchlists SET name = %s WHERE watchlist_id = %s",
                    (name, watchlist_id),
                )
            conn.commit()
        finally:
            self._release(conn)

    def delete_watchlist(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM watchlists WHERE watchlist_id = %s", (watchlist_id,)
                )
            conn.commit()
        finally:
            self._release(conn)

    # ── Section CRUD ─────────────────────────────────────────────

    def create_section(self, section_id, watchlist_id, name, position=0):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO watchlist_sections (section_id, watchlist_id, name, position) VALUES (%s, %s, %s, %s)",
                    (section_id, watchlist_id, name, position),
                )
            conn.commit()
        finally:
            self._release(conn)

    def list_sections(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM watchlist_sections WHERE watchlist_id = %s ORDER BY position, created_at",
                    (watchlist_id,),
                )
                return cur.fetchall()
        finally:
            self._release(conn)

    def update_section(self, section_id, name):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE watchlist_sections SET name = %s WHERE section_id = %s",
                    (name, section_id),
                )
            conn.commit()
        finally:
            self._release(conn)

    def delete_section(self, section_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM watchlist_sections WHERE section_id = %s",
                    (section_id,),
                )
            conn.commit()
        finally:
            self._release(conn)

    # ── Item CRUD ────────────────────────────────────────────────

    def add_watchlist_item(
        self,
        item_id,
        watchlist_id,
        symbol,
        asset_type,
        display_name=None,
        section_id=None,
    ):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO watchlist_items (item_id, watchlist_id, section_id, symbol, asset_type, display_name) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        item_id,
                        watchlist_id,
                        section_id,
                        symbol,
                        asset_type,
                        display_name,
                    ),
                )
            conn.commit()
        finally:
            self._release(conn)

    def remove_watchlist_item(self, item_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM watchlist_items WHERE item_id = %s", (item_id,)
                )
            conn.commit()
        finally:
            self._release(conn)

    def get_watchlist_items(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT wi.*, ws.name AS section_name, ws.position AS section_position
                    FROM watchlist_items wi
                    LEFT JOIN watchlist_sections ws ON wi.section_id = ws.section_id
                    WHERE wi.watchlist_id = %s
                    ORDER BY ws.position, ws.created_at, wi.position, wi.created_at
                """,
                    (watchlist_id,),
                )
                return cur.fetchall()
        finally:
            self._release(conn)

    def move_item_to_section(self, item_id, section_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE watchlist_items SET section_id = %s WHERE item_id = %s",
                    (section_id, item_id),
                )
            conn.commit()
        finally:
            self._release(conn)

    def set_item_pinned(self, item_id, is_pinned):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE watchlist_items SET is_pinned = %s WHERE item_id = %s",
                    (bool(is_pinned), item_id),
                )
            conn.commit()
        finally:
            self._release(conn)

    def get_pinned_items(self, user_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT wi.*
                    FROM watchlist_items wi
                    JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                    WHERE wl.user_id = %s AND wi.is_pinned = TRUE
                    ORDER BY wi.created_at
                    LIMIT 3
                """,
                    (user_id,),
                )
                return cur.fetchall()
        finally:
            self._release(conn)

    def count_pinned_items(self, user_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM watchlist_items wi
                    JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                    WHERE wl.user_id = %s AND wi.is_pinned = TRUE
                """,
                    (user_id,),
                )
                row = cur.fetchone()
                return row["cnt"] if row else 0
        finally:
            self._release(conn)

    def get_all_watched_symbols(self):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT DISTINCT symbol, asset_type FROM watchlist_items")
                return cur.fetchall()
        finally:
            self._release(conn)

    def get_ticker_notes(self, user_id: str, symbol: str) -> list:
        """Return all notes for a user+ticker, newest first."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, title, content, created_at
                    FROM ticker_notes
                    WHERE user_id = %s AND symbol = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id, symbol.upper()),
                )
                return cur.fetchall()
        finally:
            self._release(conn)

    def create_ticker_note(
        self, user_id: str, symbol: str, title: str, content: str
    ) -> None:
        """Insert a new note for a user+ticker."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ticker_notes (user_id, symbol, title, content)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, symbol.upper(), title or "", content or ""),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create ticker note: {e}")
        finally:
            if conn:
                self._release(conn)

    def update_ticker_note(
        self, note_id: int, user_id: str, title: str, content: str
    ) -> None:
        """Update an existing note — ownership enforced via user_id."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ticker_notes
                    SET title = %s, content = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                    """,
                    (title or "", content or "", note_id, user_id),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to update ticker note: {e}")
        finally:
            if conn:
                self._release(conn)

    def delete_ticker_note(self, note_id: int, user_id: str) -> None:
        """Delete a note — ownership enforced via user_id."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ticker_notes WHERE id = %s AND user_id = %s",
                    (note_id, user_id),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to delete ticker note: {e}")
        finally:
            if conn:
                self._release(conn)

    def get_watched_symbols_for_user(self, user_id):
        """Return all watched symbols for a specific user."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT wi.symbol, wi.asset_type
                    FROM watchlist_items wi
                    JOIN watchlists w ON wi.watchlist_id = w.watchlist_id
                    WHERE w.user_id = %s
                """,
                    (user_id,),
                )
                return cur.fetchall()
        finally:
            self._release(conn)

    # ── Price Cache ──────────────────────────────────────────────

    def upsert_price_cache(
        self, symbol, asset_type, price, change_percent, display_name=None
    ):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO price_cache (symbol, asset_type, price, change_percent, display_name, last_updated)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                        price          = EXCLUDED.price,
                        change_percent = EXCLUDED.change_percent,
                        display_name   = COALESCE(EXCLUDED.display_name, price_cache.display_name),
                        last_updated   = NOW()
                """,
                    (symbol, asset_type, price, change_percent, display_name),
                )
            conn.commit()
        finally:
            self._release(conn)
        try:
            if os.getenv("STOCKPRO_ALERT_EVAL_ENABLED", "true").lower() in (
                "1",
                "true",
                "yes",
            ):
                from alerts.evaluation import evaluate_alerts_for_symbols

                evaluate_alerts_for_symbols(self, [symbol])
        except Exception:
            logger.exception("price alert evaluation failed after cache upsert")

    def get_cached_prices(self, symbols):
        if not symbols:
            return {}
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                placeholders = ",".join(["%s"] * len(symbols))
                cur.execute(
                    f"SELECT * FROM price_cache WHERE symbol IN ({placeholders})",
                    list(symbols),
                )
                rows = cur.fetchall()
                return {row["symbol"]: row for row in rows}
        finally:
            self._release(conn)

    def get_all_cached_prices(self):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM price_cache")
                rows = cur.fetchall()
                return {row["symbol"]: row for row in rows}
        finally:
            self._release(conn)

    # ==================== Price alerts ====================

    def create_price_alert(
        self,
        alert_id: str,
        user_id: str,
        symbol: str,
        direction: str,
        target_price: float,
        asset_type: str = "stock",
    ) -> None:
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO price_alerts
                    (alert_id, user_id, symbol, asset_type, direction, target_price)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (alert_id, user_id, symbol, asset_type, direction, target_price),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create price alert: {e}")
        finally:
            if conn:
                self._release(conn)

    def list_price_alerts_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM price_alerts
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )
                return list(cur.fetchall())
        finally:
            self._release(conn)

    def delete_price_alert(self, alert_id: str, user_id: str) -> bool:
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM price_alerts
                    WHERE alert_id = %s AND user_id = %s
                    """,
                    (alert_id, user_id),
                )
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to delete price alert: {e}")
        finally:
            if conn:
                self._release(conn)

    def set_price_alert_active(self, alert_id: str, user_id: str, active: bool) -> bool:
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE price_alerts SET active = %s
                    WHERE alert_id = %s AND user_id = %s
                    """,
                    (active, alert_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
            return ok
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to update price alert: {e}")
        finally:
            if conn:
                self._release(conn)

    def list_active_alerts_for_symbols(
        self, symbols: List[str]
    ) -> List[Dict[str, Any]]:
        if not symbols:
            return []
        norm = [s.upper() for s in symbols]
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM price_alerts
                    WHERE active = TRUE AND symbol = ANY(%s)
                    """,
                    (norm,),
                )
                return list(cur.fetchall())
        finally:
            self._release(conn)

    def record_price_alert_trigger(
        self,
        notification_id: str,
        user_id: str,
        alert_id: str,
        symbol: str,
        body: str,
    ) -> None:
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO price_alert_notifications
                    (notification_id, user_id, alert_id, symbol, body)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (notification_id, user_id, alert_id, symbol, body),
                )
                cur.execute(
                    """
                    UPDATE price_alerts
                    SET last_triggered_at = NOW()
                    WHERE alert_id = %s
                    """,
                    (alert_id,),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to record price alert trigger: {e}")
        finally:
            if conn:
                self._release(conn)

    def list_price_alert_notifications_for_user(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM price_alert_notifications
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                return list(cur.fetchall())
        finally:
            self._release(conn)

    def count_unread_price_alert_notifications(self, user_id: str) -> int:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM price_alert_notifications
                    WHERE user_id = %s AND read_at IS NULL
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            self._release(conn)

    def mark_price_alert_notification_read(
        self, notification_id: str, user_id: str
    ) -> bool:
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE price_alert_notifications
                    SET read_at = NOW()
                    WHERE notification_id = %s AND user_id = %s AND read_at IS NULL
                    """,
                    (notification_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
            return ok
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to mark notification read: {e}")
        finally:
            if conn:
                self._release(conn)

    # ==================== CSV Import Logging ====================

    def log_csv_import(
        self,
        import_id: str,
        portfolio_id: str,
        filename: str,
        row_count: int,
        success_count: int,
        error_count: int,
        errors_json: List[Dict[str, Any]],
    ):
        """Log a CSV import operation."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO csv_imports
                    (import_id, portfolio_id, filename, row_count, success_count, error_count, errors_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        import_id,
                        portfolio_id,
                        filename,
                        row_count,
                        success_count,
                        error_count,
                        json.dumps(errors_json) if errors_json else None,
                    ),
                )
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to log CSV import: {e}")
        finally:
            self._release(conn)


# Global instance (thread-safe singleton — concurrent init_schema causes PostgreSQL
# "tuple concurrently updated" when DDL runs from multiple connections at once)
_db_manager: Optional[DatabaseManager] = None
_db_manager_lock = threading.Lock()


def get_database_manager() -> DatabaseManager:
    """Get or create global database manager instance."""
    global _db_manager
    if _db_manager is None:
        with _db_manager_lock:
            if _db_manager is None:
                _db_manager = DatabaseManager()
                _db_manager.init_schema()
    return _db_manager
