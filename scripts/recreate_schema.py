"""
Script to recreate the database schema in Supabase (PostgreSQL).
Requires DATABASE_URL to be set in .env.
"""

import os
import sys
from dotenv import load_dotenv

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    load_dotenv()
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")

def recreate_schema():
    """Recreate the database schema."""
    if not os.getenv('DATABASE_URL'):
        print("ERROR: DATABASE_URL environment variable not set.")
        print("Set it to your Supabase direct connection string in .env")
        sys.exit(1)

    print("Recreating database schema...")
    from database import DatabaseManager

    try:
        db_manager = DatabaseManager()
        db_manager.init_schema()
        print("✓ Schema recreation complete!")
    except Exception as e:
        print(f"✗ Error recreating schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    recreate_schema()
