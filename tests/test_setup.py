"""
Quick setup validation script.
Run this to verify your environment is configured correctly.
"""

import os
import sys
from pathlib import Path


def check_environment():
    """Check if environment is set up correctly."""
    print("Checking environment setup...\n")

    errors = []
    warnings = []

    # Check Python version
    if sys.version_info < (3, 10):
        errors.append(f"Python 3.10+ required, found {sys.version}")
    else:
        print(f"✓ Python version: {sys.version.split()[0]}")

    # Check for .env file
    env_file = Path(".env")
    if not env_file.exists():
        warnings.append(".env file not found. Please create it from .env.example")
    else:
        print("✓ .env file exists")

    # Check for required environment variables
    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        errors.append("DATABASE_URL not set in .env file (PostgreSQL / Supabase connection string)")
    else:
        print("✓ DATABASE_URL is set")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        errors.append("GEMINI_API_KEY not set in .env file (required for research and embeddings)")
    else:
        print("✓ GEMINI_API_KEY is set")

    flask_secret = os.getenv("FLASK_SECRET_KEY")
    if not flask_secret:
        errors.append("FLASK_SECRET_KEY not set in .env file")
    else:
        print("✓ FLASK_SECRET_KEY is set")

    clerk_secret = os.getenv("CLERK_SECRET_KEY")
    if not clerk_secret:
        errors.append("CLERK_SECRET_KEY not set in .env file")
    else:
        print("✓ CLERK_SECRET_KEY is set")

    alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not alpha_vantage_key:
        warnings.append("ALPHA_VANTAGE_API_KEY not set in .env file (may be in mcp.json)")
    else:
        print("✓ ALPHA_VANTAGE_API_KEY is set")

    # Check for mcp.json
    mcp_file = Path("mcp.json")
    if not mcp_file.exists():
        warnings.append("mcp.json not found. Please create it from mcp.json.example")
    else:
        print("✓ mcp.json exists")
        try:
            import json

            with open(mcp_file) as f:
                mcp_config = json.load(f)
            if "YOUR_API_KEY" in str(mcp_config):
                warnings.append("mcp.json contains placeholder API key")
            else:
                print("✓ mcp.json appears to be configured")
        except Exception as e:
            warnings.append(f"Could not parse mcp.json: {e}")

    # Check for required packages
    required_packages = ["flask", "psycopg2", "python_dotenv", "langgraph"]
    missing_packages = []

    for package in required_packages:
        mod = package.replace("-", "_")
        if mod == "python_dotenv":
            mod = "dotenv"
        try:
            __import__(mod)
            print(f"✓ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            errors.append(f"{package} is not installed")

    # Summary
    print("\n" + "=" * 50)
    if errors:
        print("❌ ERRORS FOUND:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease fix these errors before running the application.")
        return False
    else:
        print("✓ No critical errors found")

    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
        print("\nThese warnings may not prevent the app from running, but should be addressed.")

    print("\n" + "=" * 50)
    print("Setup validation complete!")
    return len(errors) == 0


if __name__ == "__main__":
    success = check_environment()
    sys.exit(0 if success else 1)
