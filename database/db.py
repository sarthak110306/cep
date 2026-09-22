import mysql.connector
from mysql.connector import Error
from config import Config


def get_db_connection():
    """Create and return a MySQL database connection with support for custom ports and SSL."""
    connect_kwargs = {
        "host": Config.DB_HOST,
        "port": Config.DB_PORT,
        "user": Config.DB_USER,
        "password": Config.DB_PASSWORD,
        "database": Config.DB_NAME,
        "autocommit": False,
    }

    if Config.DB_SSL_DISABLED:
        connect_kwargs["ssl_disabled"] = True
    elif Config.DB_SSL_CA:
        connect_kwargs["ssl_ca"] = Config.DB_SSL_CA
        connect_kwargs["ssl_verify_cert"] = Config.DB_SSL_VERIFY_CERT

    try:
        connection = mysql.connector.connect(**connect_kwargs)
        return connection
    except Error as exc:
        raise RuntimeError(
            f"Database connection failed to {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME} as '{Config.DB_USER}': {exc}"
        ) from exc


def dict_cursor(connection):
    """Return a cursor that yields rows as dictionaries."""
    return connection.cursor(dictionary=True)
