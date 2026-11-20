import zlib

SHARDS = 4


def shard_for(event_id=None, actor_id=None) -> int:
    """Event actions hash event_id; other actions hash actor_id.
    crc32 is stable across processes (Python's hash() is not)."""
    key = event_id if event_id is not None else actor_id
    if key is None:          # e.g. LOGIN_FAILED with unknown user
        return 0
    return zlib.crc32(str(key).encode()) % SHARDS


def table_for(event_id=None, actor_id=None) -> str:
    return f"audit_logs_{shard_for(event_id, actor_id)}"