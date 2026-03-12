"""
PostgreSQL Database Connection Utility

Supports multi-user mode with connection pooling.
Provides placeholder conversion for backward compatibility with legacy code.
"""
import os
import threading
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Try to import psycopg2
try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    logger.warning("psycopg2 not installed. PostgreSQL support disabled.")

# Connection pool (global singleton)
_connection_pool: Optional[Any] = None
_pool_lock = threading.Lock()


def _get_database_url() -> str:
    """Get database connection URL from environment"""
    return os.getenv('DATABASE_URL', '').strip()


def _parse_database_url(url: str) -> Dict[str, Any]:
    """
    Parse DATABASE_URL format: postgresql://user:password@host:port/dbname
    """
    if not url:
        return {}
    
    # Remove protocol prefix
    if url.startswith('postgresql://'):
        url = url[13:]
    elif url.startswith('postgres://'):
        url = url[11:]
    else:
        return {}
    
    result = {}
    
    # Split user:password@host:port/dbname
    if '@' in url:
        auth, hostpart = url.rsplit('@', 1)
        if ':' in auth:
            result['user'], result['password'] = auth.split(':', 1)
        else:
            result['user'] = auth
    else:
        hostpart = url
    
    # Split host:port/dbname
    if '/' in hostpart:
        hostport, result['dbname'] = hostpart.split('/', 1)
    else:
        hostport = hostpart
    
    if ':' in hostport:
        result['host'], port_str = hostport.split(':', 1)
        result['port'] = int(port_str)
    else:
        result['host'] = hostport
        result['port'] = 5432
    
    return result


def _get_connection_pool():
    """Get or create connection pool"""
    global _connection_pool
    
    if _connection_pool is not None:
        return _connection_pool
    
    with _pool_lock:
        if _connection_pool is not None:
            return _connection_pool
        
        if not HAS_PSYCOPG2:
            raise RuntimeError("psycopg2 is not installed. Cannot use PostgreSQL.")
        
        db_url = _get_database_url()
        if not db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        
        params = _parse_database_url(db_url)
        if not params:
            raise RuntimeError(f"Invalid DATABASE_URL format: {db_url}")
        
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                host=params.get('host', 'localhost'),
                port=params.get('port', 5432),
                user=params.get('user', 'quantdinger'),
                password=params.get('password', ''),
                dbname=params.get('dbname', 'quantdinger'),
                connect_timeout=10,
            )
            logger.info(f"PostgreSQL connection pool created: {params.get('host')}:{params.get('port')}/{params.get('dbname')}")
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL connection pool: {e}")
            raise
        
        return _connection_pool


class PostgresCursor:
    """PostgreSQL cursor wrapper with placeholder conversion for backward compatibility"""
    
    def __init__(self, cursor):
        self._cursor = cursor
        self._last_insert_id = None
    
    def _convert_placeholders(self, query: str) -> str:
        """
        Convert ? placeholders to PostgreSQL %s for backward compatibility.
        Also handle some SQL syntax differences.
        """
        # Replace ? -> %s
        query = query.replace('?', '%s')
        
        # INSERT OR IGNORE -> PostgreSQL: INSERT ... ON CONFLICT DO NOTHING
        query = query.replace('INSERT OR IGNORE', 'INSERT')
        
        return query
    
    def execute(self, query: str, args: Any = None):
        """Execute SQL statement"""
        query = self._convert_placeholders(query)
        
        # Check if this is an INSERT and add RETURNING id if not present
        is_insert = query.strip().upper().startswith('INSERT')
        if is_insert and 'RETURNING' not in query.upper():
            query = query.rstrip(';').rstrip() + ' RETURNING id'
        
        if args:
            if not isinstance(args, (tuple, list)):
                args = (args,)
            result = self._cursor.execute(query, args)
        else:
            result = self._cursor.execute(query)
        
        # Capture last insert id for INSERT statements
        if is_insert:
            try:
                row = self._cursor.fetchone()
                if row and 'id' in row:
                    self._last_insert_id = row['id']
            except Exception:
                pass
        
        return result
    
    def fetchone(self) -> Optional[Dict[str, Any]]:
        """Fetch single row"""
        row = self._cursor.fetchone()
        if row is None:
            return None
        # RealDictCursor already returns a dict, so return as-is
        return row if isinstance(row, dict) else dict(row) if row else None
    
    def fetchall(self) -> List[Dict[str, Any]]:
        """Fetch all rows"""
        rows = self._cursor.fetchall()
        if not rows:
            return []
        # RealDictCursor already returns dicts, so return as-is
        return [row if isinstance(row, dict) else dict(row) for row in rows]
    
    def close(self):
        """Close cursor"""
        self._cursor.close()
    
    @property
    def lastrowid(self) -> Optional[int]:
        """Get last inserted row ID"""
        return self._last_insert_id
    
    @property
    def rowcount(self) -> int:
        """Get affected row count"""
        return self._cursor.rowcount


class PostgresConnection:
    """PostgreSQL connection wrapper"""
    
    def __init__(self, conn):
        self._conn = conn
        self._pool = _get_connection_pool()
    
    def cursor(self) -> PostgresCursor:
        """Create cursor"""
        return PostgresCursor(self._conn.cursor(cursor_factory=RealDictCursor))
    
    def commit(self):
        """Commit transaction"""
        self._conn.commit()
    
    def rollback(self):
        """Rollback transaction"""
        self._conn.rollback()
    
    def close(self):
        """Return connection to pool"""
        if self._pool and self._conn:
            try:
                self._pool.putconn(self._conn)
            except Exception as e:
                logger.warning(f"Failed to return connection to pool: {e}")


@contextmanager
def get_pg_connection():
    """
    Get PostgreSQL database connection (Context Manager)
    """
    pool = _get_connection_pool()
    conn = None
    try:
        conn = pool.getconn()
        pg_conn = PostgresConnection(conn)
        yield pg_conn
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        # 记录更详细的错误信息
        error_msg = str(e) if e else repr(e)
        error_type = type(e).__name__
        logger.error(f"PostgreSQL operation error ({error_type}): {error_msg}", exc_info=True)
        raise
    finally:
        if conn:
            try:
                pool.putconn(conn)
            except Exception:
                pass


def get_pg_connection_sync() -> PostgresConnection:
    """
    Get connection synchronously (caller must close)
    """
    pool = _get_connection_pool()
    conn = pool.getconn()
    return PostgresConnection(conn)


def execute_sql(sql: str, params: tuple = None) -> List[Dict[str, Any]]:
    """
    Execute SQL and return results (convenience function)
    """
    with get_pg_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if sql.strip().upper().startswith('SELECT'):
            return cursor.fetchall()
        conn.commit()
        return []


def is_postgres_available() -> bool:
    """Check if PostgreSQL is available"""
    if not HAS_PSYCOPG2:
        return False
    
    db_url = _get_database_url()
    if not db_url:
        return False
    
    try:
        with get_pg_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return True
    except Exception as e:
        logger.debug(f"PostgreSQL not available: {e}")
        return False


def close_pool():
    """Close connection pool (call on app shutdown)"""
    global _connection_pool
    if _connection_pool:
        try:
            _connection_pool.closeall()
            _connection_pool = None
            logger.info("PostgreSQL connection pool closed")
        except Exception as e:
            logger.warning(f"Error closing connection pool: {e}")
