"""
MySQL database connection and schema management for reports and chunks.
"""

import os
import json
import uuid
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
                    report_text TEXT NOT NULL,
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
            
            # Create report_chunks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS report_chunks (
                    chunk_id VARCHAR(36) PRIMARY KEY,
                    report_id VARCHAR(36) NOT NULL,
                    chunk_text TEXT NOT NULL,
                    section VARCHAR(100),
                    chunk_index INT NOT NULL,
                    embedding JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (report_id) REFERENCES reports(report_id) ON DELETE CASCADE,
                    INDEX idx_report_id (report_id),
                    INDEX idx_section (section)
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

    def create_user(self, user_id: str, username: str, email: str, password_hash: str):
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, email, password_hash)
                VALUES (%s, %s, %s, %s)
            """, (user_id, username, email, password_hash))
            connection.commit()
        except Error as e:
            if connection:
                connection.rollback()
            raise RuntimeError(f"Failed to create user: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT user_id, username, email, password_hash FROM users WHERE username = %s",
                (username,)
            )
            return cursor.fetchone()
        except Error as e:
            raise RuntimeError(f"Failed to get user: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
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

