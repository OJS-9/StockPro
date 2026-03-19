"""
MySQL database connection and schema management for reports, chunks, and portfolios.
"""

import os
import json
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
import mysql.connector
from mysql.connector import Error, pooling
from dotenv import load_dotenv

load_dotenv()


class DatabaseManager:
    """Manages MySQL database connections and operations for reports and chunks."""
    
    def __init__(self):
        """Initialize database manager with connection pool."""
        self.config = {
            'host': os.getenv('MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('MYSQL_PORT', 3306)),
            'user': os.getenv('MYSQL_USER'),
            'password': os.getenv('MYSQL_PASSWORD'),
            'database': os.getenv('MYSQL_DATABASE'),
            'pool_name': 'stock_research_pool',
            'pool_size': 5,
            'pool_reset_session': True
        }
        
        if not all([self.config['user'], self.config['password'], self.config['database']]):
            raise ValueError(
                "MySQL configuration incomplete. Set MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE environment variables."
            )
        
        self.connection_pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize connection pool."""
        try:
            self.connection_pool = pooling.MySQLConnectionPool(**self.config)
            print(f"✓ MySQL connection pool initialized")
        except Error as e:
            raise RuntimeError(f"Failed to create MySQL connection pool: {e}")
    
    def get_connection(self):
        """Get a connection from the pool."""
        try:
            return self.connection_pool.get_connection()
        except Error as e:
            raise RuntimeError(f"Failed to get connection from pool: {e}")
    
    def init_schema(self):
        """Initialize database schema (create tables if they don't exist)."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            # Create users table (must exist before reports due to FK)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(36) PRIMARY KEY,
                    username VARCHAR(80) NOT NULL UNIQUE,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_username (username),
                    INDEX idx_email (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create reports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    report_id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NULL,
                    ticker VARCHAR(10) NOT NULL,
                    trade_type VARCHAR(50) NOT NULL,
                    report_text MEDIUMTEXT NOT NULL,
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_ticker (ticker),
                    INDEX idx_created_at (created_at),
                    INDEX idx_user_id (user_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Inline migration: add user_id column if it doesn't exist yet
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'reports'
                  AND COLUMN_NAME = 'user_id'
            """)
            (col_exists,) = cursor.fetchone()
            if not col_exists:
                cursor.execute("""
                    ALTER TABLE reports
                    ADD COLUMN user_id VARCHAR(36) NULL AFTER report_id,
                    ADD INDEX idx_user_id (user_id)
                """)

            # Inline migration: upgrade report_text from TEXT to MEDIUMTEXT if needed
            cursor.execute("""
                SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'reports'
                  AND COLUMN_NAME = 'report_text'
            """)
            row = cursor.fetchone()
            if row and row[0] == 'text':
                cursor.execute("""
                    ALTER TABLE reports MODIFY COLUMN report_text MEDIUMTEXT NOT NULL
                """)
            
            # Create report_chunks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS report_chunks (
                    chunk_id VARCHAR(36) PRIMARY KEY,
                    report_id VARCHAR(36) NOT NULL,
                    chunk_text TEXT NOT NULL,
                    section VARCHAR(500),
                    chunk_index INT NOT NULL,
                    embedding JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (report_id) REFERENCES reports(report_id) ON DELETE CASCADE,
                    INDEX idx_report_id (report_id),
                    INDEX idx_section (section)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Inline migration: widen section column if it was created as VARCHAR(100) or VARCHAR(255)
            cursor.execute("""
                SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'report_chunks'
                  AND COLUMN_NAME = 'section'
            """)
            row = cursor.fetchone()
            if row and row[0] in (100, 255):
                cursor.execute("""
                    ALTER TABLE report_chunks MODIFY COLUMN section VARCHAR(500)
                """)

            # Create users table (must come before portfolios for FK)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(36) PRIMARY KEY,
                    username VARCHAR(80) NOT NULL UNIQUE,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NULL,
                    google_id VARCHAR(255) NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_username (username),
                    INDEX idx_email (email),
                    INDEX idx_google_id (google_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Migration: add google_id and make password_hash nullable if table already existed
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'users'
                  AND COLUMN_NAME = 'google_id'
            """)
            (google_id_exists,) = cursor.fetchone()
            if not google_id_exists:
                cursor.execute("""
                    ALTER TABLE users
                    MODIFY COLUMN password_hash VARCHAR(255) NULL,
                    ADD COLUMN google_id VARCHAR(255) NULL UNIQUE,
                    ADD INDEX idx_google_id (google_id)
                """)

            # Create portfolios table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    portfolio_id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL DEFAULT 'My Portfolio',
                    description TEXT,
                    user_id VARCHAR(36) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_portfolio_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Inline migration: add user_id column if it doesn't exist yet
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'portfolios'
                  AND COLUMN_NAME = 'user_id'
            """)
            (col_exists,) = cursor.fetchone()
            if not col_exists:
                cursor.execute("""
                    ALTER TABLE portfolios
                    ADD COLUMN user_id VARCHAR(36) NULL,
                    ADD CONSTRAINT fk_portfolio_user
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
                """)

            # Create holdings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS holdings (
                    holding_id VARCHAR(36) PRIMARY KEY,
                    portfolio_id VARCHAR(36) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    asset_type ENUM('stock', 'crypto') NOT NULL,
                    total_quantity DECIMAL(18, 8) NOT NULL DEFAULT 0,
                    average_cost DECIMAL(18, 8) NOT NULL DEFAULT 0,
                    total_cost_basis DECIMAL(18, 2) NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
                    UNIQUE KEY unique_portfolio_symbol (portfolio_id, symbol),
                    INDEX idx_portfolio_id (portfolio_id),
                    INDEX idx_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id VARCHAR(36) PRIMARY KEY,
                    holding_id VARCHAR(36) NOT NULL,
                    transaction_type ENUM('buy', 'sell') NOT NULL,
                    quantity DECIMAL(18, 8) NOT NULL,
                    price_per_unit DECIMAL(18, 8) NOT NULL,
                    fees DECIMAL(18, 2) DEFAULT 0,
                    transaction_date TIMESTAMP NOT NULL,
                    notes TEXT,
                    import_source VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (holding_id) REFERENCES holdings(holding_id) ON DELETE CASCADE,
                    INDEX idx_holding_id (holding_id),
                    INDEX idx_transaction_date (transaction_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create csv_imports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS csv_imports (
                    import_id VARCHAR(36) PRIMARY KEY,
                    portfolio_id VARCHAR(36) NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    row_count INT NOT NULL,
                    success_count INT NOT NULL,
                    error_count INT NOT NULL,
                    errors_json JSON,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
                    INDEX idx_portfolio_id (portfolio_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create watchlists table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlists (
                    watchlist_id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    name VARCHAR(100) NOT NULL DEFAULT 'My Watchlist',
                    position INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_watchlists_user_id (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create watchlist_sections table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_sections (
                    section_id VARCHAR(36) PRIMARY KEY,
                    watchlist_id VARCHAR(36) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    position INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
                    INDEX idx_sections_watchlist_id (watchlist_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create watchlist_items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_items (
                    item_id VARCHAR(36) PRIMARY KEY,
                    watchlist_id VARCHAR(36) NOT NULL,
                    section_id VARCHAR(36) NULL,
                    symbol VARCHAR(20) NOT NULL,
                    asset_type ENUM('stock', 'crypto') NOT NULL,
                    display_name VARCHAR(100) NULL,
                    position INT NOT NULL DEFAULT 0,
                    is_pinned TINYINT(1) NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
                    FOREIGN KEY (section_id) REFERENCES watchlist_sections(section_id) ON DELETE SET NULL,
                    UNIQUE KEY unique_watchlist_symbol (watchlist_id, symbol),
                    INDEX idx_items_watchlist_id (watchlist_id),
                    INDEX idx_items_section_id (section_id),
                    INDEX idx_items_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            # Create price_cache table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_cache (
                    symbol VARCHAR(20) PRIMARY KEY,
                    asset_type ENUM('stock', 'crypto') NOT NULL,
                    price DECIMAL(18, 8) NULL,
                    change_percent DECIMAL(10, 4) NULL,
                    display_name VARCHAR(100) NULL,
                    last_updated TIMESTAMP NULL,
                    INDEX idx_price_cache_last_updated (last_updated)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)

            connection.commit()
            print("✓ Database schema initialized")

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to initialize schema: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
    
    def save_report(
        self,
        ticker: str,
        trade_type: str,
        report_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Save a report to the database.

        Args:
            ticker: Stock ticker symbol
            trade_type: Type of trade
            report_text: Full report text
            metadata: Optional metadata dictionary
            user_id: Optional user ID for ownership

        Returns:
            report_id: Generated report ID
        """
        report_id = str(uuid.uuid4())
        connection = None

        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            metadata_json = json.dumps(metadata) if metadata else None

            cursor.execute("""
                INSERT INTO reports (report_id, user_id, ticker, trade_type, report_text, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (report_id, user_id, ticker.upper(), trade_type, report_text, metadata_json))
            
            connection.commit()
            return report_id
            
        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to save report: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
    
    def get_report(self, report_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve a report by ID, optionally verifying ownership.

        Args:
            report_id: Report ID
            user_id: If provided, only return the report if it belongs to this user

        Returns:
            Report dictionary or None if not found / not owned by user
        """
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            if user_id:
                cursor.execute("""
                    SELECT report_id, user_id, ticker, trade_type, report_text, metadata, created_at
                    FROM reports
                    WHERE report_id = %s AND user_id = %s
                """, (report_id, user_id))
            else:
                cursor.execute("""
                    SELECT report_id, user_id, ticker, trade_type, report_text, metadata, created_at
                    FROM reports
                    WHERE report_id = %s
                """, (report_id,))

            result = cursor.fetchone()
            if result and result.get('metadata'):
                result['metadata'] = json.loads(result['metadata'])

            return result

        except Error as e:
            raise RuntimeError(f"Failed to get report: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    
    def get_reports_by_ticker(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent reports for a ticker.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT report_id, ticker, trade_type, report_text, metadata, created_at
                FROM reports
                WHERE ticker = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (ticker.upper(), limit))

            results = cursor.fetchall()
            for result in results:
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])

            return results

        except Error as e:
            raise RuntimeError(f"Failed to get reports by ticker: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_all_reports(
        self,
        ticker: Optional[str] = None,
        trade_type: Optional[str] = None,
        sort_order: str = "DESC",
        limit: int = 20,
        offset: int = 0,
        user_id: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Get paginated reports with optional filtering.

        Args:
            ticker: Optional ticker filter
            trade_type: Optional trade type filter
            sort_order: Sort order for created_at (ASC or DESC)
            limit: Maximum number of reports to return
            offset: Number of reports to skip
            user_id: If provided, only return reports belonging to this user

        Returns:
            Tuple of (reports list, total count)
        """
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            # Build WHERE clause dynamically
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

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            # Validate sort order
            sort_order = "DESC" if sort_order.upper() not in ("ASC", "DESC") else sort_order.upper()

            # Get total count
            count_sql = f"SELECT COUNT(*) as total FROM reports {where_sql}"
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()['total']

            # Get paginated results
            query_sql = f"""
                SELECT report_id, user_id, ticker, trade_type, report_text, metadata, created_at
                FROM reports
                {where_sql}
                ORDER BY created_at {sort_order}
                LIMIT %s OFFSET %s
            """
            cursor.execute(query_sql, params + [limit, offset])

            results = cursor.fetchall()
            for result in results:
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])

            return results, total_count

        except Error as e:
            raise RuntimeError(f"Failed to get all reports: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    
    def save_chunks(
        self,
        report_id: str,
        chunks: List[Dict[str, Any]]
    ):
        """
        Save report chunks with embeddings.
        
        Args:
            report_id: Report ID
            chunks: List of chunk dictionaries with keys:
                - chunk_text: Text content
                - section: Section name (optional)
                - chunk_index: Index in report
                - embedding: Embedding vector (list of floats)
        """
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            for chunk in chunks:
                chunk_id = str(uuid.uuid4())
                embedding_json = json.dumps(chunk.get('embedding')) if chunk.get('embedding') else None
                
                cursor.execute("""
                    INSERT INTO report_chunks 
                    (chunk_id, report_id, chunk_text, section, chunk_index, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    chunk_id,
                    report_id,
                    chunk['chunk_text'],
                    chunk.get('section'),
                    chunk['chunk_index'],
                    embedding_json
                ))
            
            connection.commit()
            
        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to save chunks: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
    
    def get_chunks_by_report(
        self,
        report_id: str,
        include_embeddings: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all chunks for a report.
        
        Args:
            report_id: Report ID
            include_embeddings: Whether to include embeddings in results
        
        Returns:
            List of chunk dictionaries
        """
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            if include_embeddings:
                cursor.execute("""
                    SELECT chunk_id, report_id, chunk_text, section, chunk_index, embedding, created_at
                    FROM report_chunks
                    WHERE report_id = %s
                    ORDER BY chunk_index ASC
                """, (report_id,))
            else:
                cursor.execute("""
                    SELECT chunk_id, report_id, chunk_text, section, chunk_index, created_at
                    FROM report_chunks
                    WHERE report_id = %s
                    ORDER BY chunk_index ASC
                """, (report_id,))
            
            results = cursor.fetchall()
            for result in results:
                if result.get('embedding'):
                    result['embedding'] = json.loads(result['embedding'])
            
            return results
            
        except Error as e:
            raise RuntimeError(f"Failed to get chunks: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
    
    def delete_report(self, report_id: str):
        """
        Delete a report and all its chunks (cascade).

        Args:
            report_id: Report ID
        """
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("DELETE FROM reports WHERE report_id = %s", (report_id,))
            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to delete report: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    # ==================== Portfolio Methods ====================

    def create_portfolio(
        self,
        portfolio_id: str,
        name: str = "My Portfolio",
        description: str = "",
        user_id: Optional[str] = None
    ):
        """Create a new portfolio."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO portfolios (portfolio_id, name, description, user_id)
                VALUES (%s, %s, %s, %s)
            """, (portfolio_id, name, description, user_id))

            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to create portfolio: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """Get portfolio by ID."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT portfolio_id, name, description, user_id, created_at, updated_at
                FROM portfolios
                WHERE portfolio_id = %s
            """, (portfolio_id,))

            return cursor.fetchone()

        except Error as e:
            raise RuntimeError(f"Failed to get portfolio: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def list_portfolios(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List portfolios, optionally filtered by user."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            if user_id is not None:
                cursor.execute("""
                    SELECT portfolio_id, name, description, user_id, created_at, updated_at
                    FROM portfolios
                    WHERE user_id = %s
                    ORDER BY created_at ASC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT portfolio_id, name, description, user_id, created_at, updated_at
                    FROM portfolios
                    ORDER BY created_at ASC
                """)

            return cursor.fetchall()

        except Error as e:
            raise RuntimeError(f"Failed to list portfolios: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    # ==================== User Methods ====================

    def create_user(
        self,
        user_id: str,
        username: str,
        email: str,
        password_hash: Optional[str] = None,
        google_id: Optional[str] = None,
    ):
        """Create a new user. password_hash and google_id are optional (e.g. Google-only users)."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, email, password_hash, google_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, username, email, password_hash, google_id))

            connection.commit()
        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to create user: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a user by username."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT user_id, username, email, password_hash, google_id, created_at
                FROM users
                WHERE username = %s
            """, (username,))

            return cursor.fetchone()

        except Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT user_id, username, email, password_hash, google_id, created_at
                FROM users
                WHERE user_id = %s
            """, (user_id,))

            return cursor.fetchone()

        except Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT user_id, username, email, password_hash, google_id, created_at
                FROM users
                WHERE email = %s
            """, (email,))

            return cursor.fetchone()

        except Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by Google OAuth sub (google_id)."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT user_id, username, email, password_hash, google_id, created_at
                FROM users
                WHERE google_id = %s
            """, (google_id,))

            return cursor.fetchone()

        except Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def update_user_google_id(self, user_id: str, google_id: str):
        """Link a Google account to an existing user."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("""
                UPDATE users SET google_id = %s WHERE user_id = %s
            """, (google_id, user_id))

            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to update user: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    # ==================== Holdings Methods ====================

    def create_holding(
        self,
        holding_id: str,
        portfolio_id: str,
        symbol: str,
        asset_type: str
    ):
        """Create a new holding."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO holdings (holding_id, portfolio_id, symbol, asset_type)
                VALUES (%s, %s, %s, %s)
            """, (holding_id, portfolio_id, symbol.upper(), asset_type))

            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to create holding: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_holding(self, portfolio_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific holding by portfolio and symbol."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT holding_id, portfolio_id, symbol, asset_type,
                       total_quantity, average_cost, total_cost_basis,
                       created_at, updated_at
                FROM holdings
                WHERE portfolio_id = %s AND symbol = %s
            """, (portfolio_id, symbol.upper()))

            result = cursor.fetchone()
            if result:
                # Convert Decimal to Decimal for consistency
                result['total_quantity'] = Decimal(str(result['total_quantity']))
                result['average_cost'] = Decimal(str(result['average_cost']))
                result['total_cost_basis'] = Decimal(str(result['total_cost_basis']))
            return result

        except Error as e:
            raise RuntimeError(f"Failed to get holding: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_holding_by_id(self, holding_id: str) -> Optional[Dict[str, Any]]:
        """Get a holding by its ID."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT holding_id, portfolio_id, symbol, asset_type,
                       total_quantity, average_cost, total_cost_basis,
                       created_at, updated_at
                FROM holdings
                WHERE holding_id = %s
            """, (holding_id,))

            result = cursor.fetchone()
            if result:
                result['total_quantity'] = Decimal(str(result['total_quantity']))
                result['average_cost'] = Decimal(str(result['average_cost']))
                result['total_cost_basis'] = Decimal(str(result['total_cost_basis']))
            return result

        except Error as e:
            raise RuntimeError(f"Failed to get holding: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_holdings(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """Get all holdings for a portfolio."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT holding_id, portfolio_id, symbol, asset_type,
                       total_quantity, average_cost, total_cost_basis,
                       created_at, updated_at
                FROM holdings
                WHERE portfolio_id = %s
                ORDER BY symbol ASC
            """, (portfolio_id,))

            results = cursor.fetchall()
            for result in results:
                result['total_quantity'] = Decimal(str(result['total_quantity']))
                result['average_cost'] = Decimal(str(result['average_cost']))
                result['total_cost_basis'] = Decimal(str(result['total_cost_basis']))
            return results

        except Error as e:
            raise RuntimeError(f"Failed to get holdings: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def update_holding(
        self,
        holding_id: str,
        total_quantity: Decimal,
        average_cost: Decimal,
        total_cost_basis: Decimal
    ):
        """Update holding totals."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("""
                UPDATE holdings
                SET total_quantity = %s,
                    average_cost = %s,
                    total_cost_basis = %s
                WHERE holding_id = %s
            """, (str(total_quantity), str(average_cost), str(total_cost_basis), holding_id))

            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to update holding: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def delete_holding(self, holding_id: str):
        """Delete a holding and all its transactions (cascade)."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("DELETE FROM holdings WHERE holding_id = %s", (holding_id,))
            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to delete holding: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

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
        import_source: str = "manual"
    ):
        """Add a transaction to a holding."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO transactions
                (transaction_id, holding_id, transaction_type, quantity,
                 price_per_unit, fees, transaction_date, notes, import_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                transaction_id,
                holding_id,
                transaction_type,
                str(quantity),
                str(price_per_unit),
                str(fees),
                transaction_date,
                notes,
                import_source
            ))

            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to add transaction: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get a transaction by ID."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT transaction_id, holding_id, transaction_type, quantity,
                       price_per_unit, fees, transaction_date, notes, import_source,
                       created_at
                FROM transactions
                WHERE transaction_id = %s
            """, (transaction_id,))

            result = cursor.fetchone()
            if result:
                result['quantity'] = Decimal(str(result['quantity']))
                result['price_per_unit'] = Decimal(str(result['price_per_unit']))
                result['fees'] = Decimal(str(result['fees']))
            return result

        except Error as e:
            raise RuntimeError(f"Failed to get transaction: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_transactions(self, holding_id: str) -> List[Dict[str, Any]]:
        """Get all transactions for a holding."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT transaction_id, holding_id, transaction_type, quantity,
                       price_per_unit, fees, transaction_date, notes, import_source,
                       created_at
                FROM transactions
                WHERE holding_id = %s
                ORDER BY transaction_date ASC
            """, (holding_id,))

            results = cursor.fetchall()
            for result in results:
                result['quantity'] = Decimal(str(result['quantity']))
                result['price_per_unit'] = Decimal(str(result['price_per_unit']))
                result['fees'] = Decimal(str(result['fees']))
            return results

        except Error as e:
            raise RuntimeError(f"Failed to get transactions: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def delete_transaction(self, transaction_id: str):
        """Delete a transaction."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            cursor.execute("DELETE FROM transactions WHERE transaction_id = %s", (transaction_id,))
            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to delete transaction: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    def get_all_portfolio_transactions(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """Get all transactions for a portfolio joined with holding symbol and asset_type."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT t.transaction_id, t.holding_id, t.transaction_type, t.quantity,
                       t.price_per_unit, t.fees, t.transaction_date, t.notes,
                       h.symbol, h.asset_type
                FROM transactions t
                JOIN holdings h ON t.holding_id = h.holding_id
                WHERE h.portfolio_id = %s
                ORDER BY t.transaction_date ASC
            """, (portfolio_id,))

            results = cursor.fetchall()
            for result in results:
                result['quantity'] = Decimal(str(result['quantity']))
                result['price_per_unit'] = Decimal(str(result['price_per_unit']))
                result['fees'] = Decimal(str(result['fees']))
            return results

        except Error as e:
            raise RuntimeError(f"Failed to get portfolio transactions: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    # ==================== Watchlist Methods ====================

    def create_watchlist(self, watchlist_id, user_id, name='My Watchlist'):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO watchlists (watchlist_id, user_id, name) VALUES (%s, %s, %s)",
                    (watchlist_id, user_id, name)
                )
            conn.commit()
        finally:
            conn.close()

    def get_watchlist(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM watchlists WHERE watchlist_id = %s", (watchlist_id,))
                return cursor.fetchone()
        finally:
            conn.close()

    def list_watchlists(self, user_id):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(
                    "SELECT * FROM watchlists WHERE user_id = %s ORDER BY position, created_at",
                    (user_id,)
                )
                return cursor.fetchall()
        finally:
            conn.close()

    def update_watchlist(self, watchlist_id, name):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE watchlists SET name = %s WHERE watchlist_id = %s",
                    (name, watchlist_id)
                )
            conn.commit()
        finally:
            conn.close()

    def delete_watchlist(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM watchlists WHERE watchlist_id = %s", (watchlist_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Section CRUD ─────────────────────────────────────────────

    def create_section(self, section_id, watchlist_id, name, position=0):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO watchlist_sections (section_id, watchlist_id, name, position) VALUES (%s, %s, %s, %s)",
                    (section_id, watchlist_id, name, position)
                )
            conn.commit()
        finally:
            conn.close()

    def list_sections(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(
                    "SELECT * FROM watchlist_sections WHERE watchlist_id = %s ORDER BY position, created_at",
                    (watchlist_id,)
                )
                return cursor.fetchall()
        finally:
            conn.close()

    def update_section(self, section_id, name):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE watchlist_sections SET name = %s WHERE section_id = %s",
                    (name, section_id)
                )
            conn.commit()
        finally:
            conn.close()

    def delete_section(self, section_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM watchlist_sections WHERE section_id = %s", (section_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Item CRUD ────────────────────────────────────────────────

    def add_watchlist_item(self, item_id, watchlist_id, symbol, asset_type, display_name=None, section_id=None):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO watchlist_items (item_id, watchlist_id, section_id, symbol, asset_type, display_name) VALUES (%s, %s, %s, %s, %s, %s)",
                    (item_id, watchlist_id, section_id, symbol, asset_type, display_name)
                )
            conn.commit()
        finally:
            conn.close()

    def remove_watchlist_item(self, item_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM watchlist_items WHERE item_id = %s", (item_id,))
            conn.commit()
        finally:
            conn.close()

    def get_watchlist_items(self, watchlist_id):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT wi.*, ws.name AS section_name, ws.position AS section_position
                    FROM watchlist_items wi
                    LEFT JOIN watchlist_sections ws ON wi.section_id = ws.section_id
                    WHERE wi.watchlist_id = %s
                    ORDER BY ws.position, ws.created_at, wi.position, wi.created_at
                """, (watchlist_id,))
                return cursor.fetchall()
        finally:
            conn.close()

    def move_item_to_section(self, item_id, section_id):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE watchlist_items SET section_id = %s WHERE item_id = %s",
                    (section_id, item_id)
                )
            conn.commit()
        finally:
            conn.close()

    def set_item_pinned(self, item_id, is_pinned):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE watchlist_items SET is_pinned = %s WHERE item_id = %s",
                    (1 if is_pinned else 0, item_id)
                )
            conn.commit()
        finally:
            conn.close()

    def get_pinned_items(self, user_id):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT wi.*
                    FROM watchlist_items wi
                    JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                    WHERE wl.user_id = %s AND wi.is_pinned = 1
                    ORDER BY wi.created_at
                    LIMIT 3
                """, (user_id,))
                return cursor.fetchall()
        finally:
            conn.close()

    def count_pinned_items(self, user_id):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) AS cnt
                    FROM watchlist_items wi
                    JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                    WHERE wl.user_id = %s AND wi.is_pinned = 1
                """, (user_id,))
                row = cursor.fetchone()
                return row['cnt'] if row else 0
        finally:
            conn.close()

    def get_all_watched_symbols(self):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT DISTINCT symbol, asset_type FROM watchlist_items")
                return cursor.fetchall()
        finally:
            conn.close()

    # ── Price Cache ──────────────────────────────────────────────

    def upsert_price_cache(self, symbol, asset_type, price, change_percent, display_name=None):
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO price_cache (symbol, asset_type, price, change_percent, display_name, last_updated)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        price = VALUES(price),
                        change_percent = VALUES(change_percent),
                        display_name = COALESCE(VALUES(display_name), display_name),
                        last_updated = NOW()
                """, (symbol, asset_type, price, change_percent, display_name))
            conn.commit()
        finally:
            conn.close()

    def get_cached_prices(self, symbols):
        if not symbols:
            return {}
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                placeholders = ','.join(['%s'] * len(symbols))
                cursor.execute(
                    f"SELECT * FROM price_cache WHERE symbol IN ({placeholders})",
                    list(symbols)
                )
                rows = cursor.fetchall()
                return {row['symbol']: row for row in rows}
        finally:
            conn.close()

    def get_all_cached_prices(self):
        conn = self.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM price_cache")
                rows = cursor.fetchall()
                return {row['symbol']: row for row in rows}
        finally:
            conn.close()

    # ==================== CSV Import Logging ====================

    def log_csv_import(
        self,
        import_id: str,
        portfolio_id: str,
        filename: str,
        row_count: int,
        success_count: int,
        error_count: int,
        errors_json: List[Dict[str, Any]]
    ):
        """Log a CSV import operation."""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()

            errors_str = json.dumps(errors_json) if errors_json else None

            cursor.execute("""
                INSERT INTO csv_imports
                (import_id, portfolio_id, filename, row_count, success_count, error_count, errors_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (import_id, portfolio_id, filename, row_count, success_count, error_count, errors_str))

            connection.commit()

        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to log CSV import: {e}")
        finally:
            if connection and connection.is_connected():
                cursor.close()                
                connection.close()


# Global instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """Get or create global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.init_schema()
    return _db_manager

