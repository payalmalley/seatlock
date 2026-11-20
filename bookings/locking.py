from functools import wraps

from django.db import IntegrityError
from django.db.utils import OperationalError

from config.db import is_lock_timeout, query
from config.errors import Conflict, LockTimeout, ValidationFailed


def lock_seats(event_id, seat_ids):
    """SELECT ... FOR UPDATE in ascending id order = a stable lock order, so two
    requests with overlapping seats can never deadlock."""
    rows = query(
        "SELECT id, status FROM seats WHERE event_id = %s AND id = ANY(%s) ORDER BY id FOR UPDATE",
        [event_id, list(seat_ids)],
    )
    if len(rows) != len(set(seat_ids)):
        raise ValidationFailed("One or more seats do not belong to this event")
    return rows


def translate_db_errors(fn):
    """Lock timeout -> 503. Unique-constraint safety net -> 409."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except OperationalError as e:
            if is_lock_timeout(e):
                raise LockTimeout("The system is busy, please retry") from e
            raise
        except IntegrityError as e:
            raise Conflict("Seat was just taken by someone else") from e
    return wrapper