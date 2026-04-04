"""Migration: convert ticker_notes from single-note to multi-note per ticker."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from database import get_database_manager

db = get_database_manager()
conn = db.get_connection()
try:
    with conn.cursor() as cur:
        # Check if id column already exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'ticker_notes' AND column_name = 'id'
        """)
        if cur.fetchone():
            print("Migration already applied — id column exists.")
        else:
            cur.execute("ALTER TABLE ticker_notes DROP CONSTRAINT ticker_notes_pkey")
            cur.execute("ALTER TABLE ticker_notes ADD COLUMN id SERIAL")
            cur.execute("ALTER TABLE ticker_notes ADD PRIMARY KEY (id)")
            cur.execute("ALTER TABLE ticker_notes ADD COLUMN title TEXT NOT NULL DEFAULT ''")
            print("Migration complete.")
    conn.commit()
except Exception as e:
    conn.rollback()
    print(f"Migration failed: {e}")
    sys.exit(1)
finally:
    db._release(conn)
