"""
Community Hackathon - Database Initialization Script for Supabase / PostgreSQL / MySQL.

Usage:
    python init_db.py
"""
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
        if stripped.startswith("--") or stripped.startswith("#"):
            continue

        chars = list(line)
        i = 0
        while i < len(chars):
            ch = chars[i]
            if ch in ("'", '"'):
                if in_quote == ch:
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
    schema_filename = "schema_postgres.sql" if Config.IS_POSTGRES else "schema.sql"
    schema_path = Path(__file__).resolve().parent / "database" / schema_filename

    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}")
        sys.exit(1)

    print(f"Connecting to {'Supabase/PostgreSQL' if Config.IS_POSTGRES else 'MySQL'} at {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}...")
    try:
        conn = get_db_connection()
    except Exception as exc:
        print(f"Failed to connect to database: {exc}")
        sys.exit(1)

    print(f"Connected successfully. Loading {schema_filename}...")
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

            if upper_prefix.startswith("CREATE DATABASE") or upper_prefix.startswith("USE "):
                skipped_count += 1
                continue

            try:
                cursor.execute(cleaned)
                conn.commit()
                executed_count += 1
            except Exception as e:
                err_str = str(e).lower()
                if "already exists" in err_str or "duplicate key" in err_str or "unique constraint" in err_str:
                    skipped_count += 1
                    conn.rollback()
                else:
                    print(f"Warning: {e}\nQuery snippet: {cleaned[:80]}...")
                    conn.rollback()

        print(f"\nDatabase initialization complete!")
        print(f"Statements executed: {executed_count}, skipped: {skipped_count}")
        print("All tables and initial problem statements, judges, events, and FAQs are ready.")
    except Exception as exc:
        conn.rollback()
        print(f"Error during schema initialization: {exc}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    init_database()
