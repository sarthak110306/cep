"""
Community Hackathon - Admin account setup script.

Issue #4 fix: the project previously shipped with a hardcoded default admin
account (admin@hackathon.local / admin123) inserted directly in
database/schema.sql and documented in README.md. That is a real security
risk - anyone who read the README or the schema file could log in as an
admin on any deployment that used the default.

This script replaces that with a safe, interactive way to create (or reset
the password of) an admin account. It does NOT delete any existing admin
account or other data; if an admin with the given email already exists, it
asks whether you want to update that account's password instead of
inserting a duplicate.

Usage (from the project root, C:\\manus code):

    python create_admin.py

You will be prompted for a name, email and password. The password is
never displayed on screen and is stored as a salted hash
(werkzeug.security.generate_password_hash), exactly like every other
password in this project - nothing is stored in plain text.
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

from config import Config
from database.db import dict_cursor, get_db_connection


def validate_email(email):
    return "@" in email and "." in email.split("@")[-1]


def main():
    print("Community Hackathon - Admin Account Setup")
    print("=" * 50)

    name = input("Admin full name: ").strip()
    if not name:
        print("Name is required.")
        sys.exit(1)

    email = input("Admin email: ").strip().lower()
    if not validate_email(email):
        print("Please enter a valid email address.")
        sys.exit(1)

    password = getpass.getpass("Admin password (min 8 characters, not shown): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    password_hash = generate_password_hash(password)

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT id FROM admins WHERE email = %s", (email,))
        existing = cursor.fetchone()

        if existing:
            answer = input(
                f"An admin with email '{email}' already exists. "
                f"Update its password instead? [y/N]: "
            ).strip().lower()
            if answer != "y":
                print("No changes made.")
                return

            cursor.execute(
                "UPDATE admins SET name = %s, password_hash = %s WHERE id = %s",
                (name, password_hash, existing["id"]),
            )
            conn.commit()
            print(f"Updated existing admin account '{email}'.")
        else:
            cursor.execute(
                "INSERT INTO admins (name, email, password_hash) VALUES (%s, %s, %s)",
                (name, email, password_hash),
            )
            conn.commit()
            print(f"Created new admin account '{email}'.")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
