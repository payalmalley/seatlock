from django.db import connection
from django.db.utils import OperationalError

LOCK_NOT_AVAILABLE = "55P03"  # Postgres lock_timeout / NOWAIT failure


def query(sql, params=None):
    """Run SQL on the current connection (so it joins any transaction.atomic()).
    Returns a list of dicts; empty list for statements without a result set."""
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        if cur.description is None:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def is_lock_timeout(exc):
    cause = getattr(exc, "__cause__", None)
    code = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    return code == LOCK_NOT_AVAILABLE