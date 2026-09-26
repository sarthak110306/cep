import os
from config import Config

if Config.IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    class PostgresDictCursorWrapper:
        """Cursor wrapper providing dictionary results and cursor.lastrowid support."""
        def __init__(self, real_cursor):
            self._cursor = real_cursor

        def __getattr__(self, name):
            return getattr(self._cursor, name)

        def __iter__(self):
            return iter(self._cursor)

        @property
        def lastrowid(self):
            """Return the last generated sequence ID using SELECT LASTVAL()."""
            try:
                self._cursor.execute("SELECT LASTVAL();")
                res = self._cursor.fetchone()
                if res:
                    return list(res.values())[0]
            except Exception:
                pass
            return None

    class PostgresConnectionWrapper:
        """Connection wrapper ensuring cursor() returns dictionary-capable cursors."""
        def __init__(self, conn):
            self._conn = conn

        def cursor(self, dictionary=True, cursor_factory=None):
            factory = RealDictCursor if (dictionary or cursor_factory is None) else cursor_factory
            return PostgresDictCursorWrapper(self._conn.cursor(cursor_factory=factory))

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def get_db_connection():
        """Create and return a Supabase/PostgreSQL database connection (IPv4 forced)."""
        import socket

        host = Config.DB_HOST
        port = Config.DB_PORT

        # Resolve hostname to IPv4 explicitly — Render free tier does not support IPv6
        try:
            ipv4_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if ipv4_info:
                host = ipv4_info[0][4][0]  # Use resolved IPv4 address directly
        except Exception:
            pass  # If resolution fails, fall back to hostname and let psycopg2 handle it

        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                sslmode=Config.DB_SSL_MODE,
                connect_timeout=15,
            )
            return PostgresConnectionWrapper(conn)
        except Exception as exc:
            raise RuntimeError(
                f"PostgreSQL connection to Supabase failed ({Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}): {exc}"
            ) from exc


    def dict_cursor(connection):
        """Return a cursor that yields rows as dictionaries."""
        return connection.cursor(dictionary=True)

else:
    import mysql.connector
    from mysql.connector import Error

    def get_db_connection():
        """Create and return a MySQL database connection."""
        connect_kwargs = {
            "host": Config.DB_HOST,
            "port": Config.DB_PORT,
            "user": Config.DB_USER,
            "password": Config.DB_PASSWORD,
            "database": Config.DB_NAME,
            "autocommit": False,
        }
        try:
            return mysql.connector.connect(**connect_kwargs)
        except Error as exc:
            raise RuntimeError(
                f"MySQL connection failed to {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}: {exc}"
            ) from exc

    def dict_cursor(connection):
        """Return a cursor that yields rows as dictionaries."""
        return connection.cursor(dictionary=True)
