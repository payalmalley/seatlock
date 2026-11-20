import json
import uuid
from datetime import datetime

from django.db import connection

from accounts.permissions import ADMIN, require_role
from audit.sharding import SHARDS, shard_for, table_for
from config.db import query
from config.errors import ValidationFailed

ACTIONS = {
    "LOGIN", "LOGIN_FAILED", "SEAT_HELD", "SEAT_HOLD_REJECTED", "HOLD_EXPIRED",
    "BOOKING_CONFIRMED", "BOOKING_CANCELLED", "EVENT_UPDATED", "CHECKIN", "ACCESS_DENIED",
}


def writeAudit(user, action, event_id=None, details=None, actor_id=None):
    """Runs on the CURRENT connection, so inside transaction.atomic() it commits or
    rolls back together with the booking. `user` may be None (failed login, expiry)."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown audit action: {action}")
    aid = actor_id if actor_id is not None else (user.id if user else None)
    table = table_for(event_id, aid)  # from a fixed list, never user input
    with connection.cursor() as cur:
        cur.execute(
            f"INSERT INTO {table} (id, actor_id, event_id, action, details, created_at) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, now())",
            [str(uuid.uuid4()), aid, event_id, action, json.dumps(details or {}, default=str)],
        )


def _encode(row):
    return f"{row['created_at'].isoformat()}|{row['id']}"


def _decode(cursor):
    try:
        ts, rid = cursor.split("|", 1)
        return datetime.fromisoformat(ts), rid
    except ValueError:
        raise ValidationFailed("Bad cursor")


def listAuditLogs(user, event_id=None, date_from=None, date_to=None, cursor=None, limit=50):
    require_role(user, ADMIN)
    # Event filter -> read ONE shard (pruning). No filter -> scatter-gather over all 4.
    shards = [shard_for(event_id=event_id)] if event_id is not None else list(range(SHARDS))

    conds, params = [], []
    if event_id is not None:
        conds.append("event_id = %s"); params.append(event_id)
    if date_from:
        conds.append("created_at >= %s"); params.append(date_from)
    if date_to:
        conds.append("created_at < %s"); params.append(date_to)
    if cursor:
        ts, rid = _decode(cursor)
        conds.append("(created_at, id::text) < (%s, %s)"); params += [ts, rid]
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    rows = []
    for i in shards:
        rows += query(
            f"SELECT id, actor_id, event_id, action, details, created_at FROM audit_logs_{i} "
            f"{where} ORDER BY created_at DESC, id::text DESC LIMIT %s",
            params + [limit],
        )
    rows.sort(key=lambda r: (r["created_at"], str(r["id"])), reverse=True)
    page = rows[:limit]
    next_cursor = _encode(page[-1]) if len(rows) > limit else None
    return {"logs": page, "next_cursor": next_cursor, "shards_queried": shards}