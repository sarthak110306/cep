"""
Community Hackathon - Database Initialization Script.

This script initializes the database tables and seed data using database/schema.sql.
It works for both local MySQL and remote cloud MySQL databases (Render, TiDB, Aiven, etc.).

Usage:
    python init_db.py
"""
import os
import re
import sys
from pathlib import Path

from config import Config
from database.db import get_db_connection


def split_sql_statements(sql_content):
    """Split SQL file contents into individual executable statements."""
    statements = []
    current_statement = []
    in_quote = None
    lines = sql_content.splitlines()

    for line in lines:
        stripped = line.strip()
        # Skip pure comment lines
        if stripped.startswith("--") or stripped.startswith("#"):
            continue

        chars = list(line)
        i = 0
        while i < len(chars):
            ch = chars[i]
            if ch in ("'", '"', "`"):
                if in_quote == ch:
                    # Check if escaped
                    if i > 0 and chars[i - 1] == "\\":
                        pass
                    else:
                        in_quote = None
                elif in_quote is None:
                    in_quote = ch
                current_statement.append(ch)
            elif ch == ";" and in_quote is None:
                stmt = "".join(current_statement).strip()
                if stmt:
                    statements.append(stmt)
                current_statement = []
            else:
                current_statement.append(ch)
            i += 1
        current_statement.append("\n")

    remainder = "".join(current_statement).strip()
    if remainder:
        statements.append(remainder)

    return statements


def init_database():
    schema_path = Path(__file__).resolve().parent / "database" / "schema.sql"
    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}")
        sys.exit(1)

    print(f"Connecting to database '{Config.DB_NAME}' on {Config.DB_HOST}:{Config.DB_PORT}...")
    try:
        conn = get_db_connection()
    except Exception as exc:
        print(f"Failed to connect to MySQL database: {exc}")
        print("\nPlease check your DB credentials in .env or Render environment variables.")
        sys.exit(1)

    print("Connected successfully. Parsing schema...")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    statements = split_sql_statements(sql_content)
    cursor = conn.cursor()
    executed_count = 0
    skipped_count = 0

    try:
        for stmt in statements:
            cleaned = stmt.strip()
            upper_prefix = cleaned[:30].upper()

            # Skip CREATE DATABASE / USE statements if connecting to a cloud-managed DB
            if upper_prefix.startswith("CREATE DATABASE") or upper_prefix.startswith("USE "):
                skipped_count += 1
                continue

            try:
                cursor.execute(cleaned)
                executed_count += 1
            except Exception as e:
                # If insert duplicates (e.g. seed data already exists), log and continue
                if "Duplicate entry" in str(e) or "already exists" in str(e):
                    skipped_count += 1
                else:
                    print(f"Warning on statement: {e}\nQuery snippet: {cleaned[:80]}...")

        conn.commit()
        print(f"\nDatabase initialization complete!")
        print(f"Statements executed: {executed_count}, skipped: {skipped_count}")
        print("All tables and initial problem statements are ready.")
    except Exception as exc:
        conn.rollback()
        print(f"Error during schema initialization: {exc}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    init_database()
