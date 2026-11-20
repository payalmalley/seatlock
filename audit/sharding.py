SHARDS = 4


def shard_for(event_id=None, actor_id=None) -> int:
    """Must match the CHECK constraints in schema.sql:
    event actions -> event_id % 4, other actions -> actor_id % 4 (anonymous -> 0)."""
    key = event_id if event_id is not None else (actor_id or 0)
    return int(key) % SHARDS


def table_for(event_id=None, actor_id=None) -> str:
    return f"audit_logs_{shard_for(event_id, actor_id)}"