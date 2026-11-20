import json

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
            f"INSERT INTO {table} (actor_id, event_id, action, details) "
            "VALUES (%s, %s, %s, %s::jsonb)",   # id and created_at come from DB defaults
            [aid, event_id, action, json.dumps(details or {}, default=str)],
        )


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
        try:
            conds.append("id < %s"); params.append(int(cursor))
        except ValueError:
            raise ValidationFailed("Bad cursor")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    rows = []
    for i in shards:   # ids come from one shared sequence, so id DESC is a valid global order
        rows += query(
            f"SELECT id, actor_id, event_id, action, details, created_at FROM audit_logs_{i} "
            f"{where} ORDER BY id DESC LIMIT %s",
            params + [limit + 1],
        )
    rows.sort(key=lambda r: r["id"], reverse=True)
    page = rows[:limit]
    next_cursor = str(page[-1]["id"]) if len(rows) > limit else None
    return {"logs": page, "next_cursor": next_cursor, "shards_queried": shards}