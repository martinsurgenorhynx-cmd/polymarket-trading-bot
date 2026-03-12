"""
Database Connection Utility - PostgreSQL Only

Provides unified interface for PostgreSQL database operations.

Usage:
    from app.utils.db import get_db_connection
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        conn.commit()

Configuration:
    DATABASE_URL=postgresql://user:password@host:port/dbname
"""

# Re-export from PostgreSQL module
from app.utils.db_postgres import (
    get_pg_connection as get_db_connection,
    get_pg_connection_sync as get_db_connection_sync,
    is_postgres_available,
    close_pool as close_db,
)


def get_db_type() -> str:
    """Get database type (always postgresql)"""
    return 'postgresql'


def is_postgres() -> bool:
    """Check if using PostgreSQL (always True)"""
    return True


def init_database():
    """
    Initialize database connection.
    Schema is created via migrations/init.sql on PostgreSQL container start.
    """
    if is_postgres_available():
        from app.utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("PostgreSQL connection verified")
    else:
        raise RuntimeError("Cannot connect to PostgreSQL. Check DATABASE_URL.")


# Legacy alias
def close_db_connection():
    """Legacy alias for close_db"""
    pass


__all__ = [
    'get_db_connection',
    'get_db_connection_sync',
    'close_db_connection',
    'init_database',
    'close_db',
    'get_db_type',
    'is_postgres',
]
