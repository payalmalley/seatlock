from django.db import transaction
from django.utils import timezone

from accounts.permissions import ADMIN, ORGANIZER, require_role
from audit.services import writeAudit
from config.db import query, query_one
from config.errors import ValidationFailed

MAX_ROWS = 26
MAX_SEATS_PER_ROW = 30


def createEvent(user, title, description, venue, starts_at, rows, seats_per_row):
    """Create a PUBLISHED event owned by `user`, with rows A.. x seats 1..N."""
    require_role(user, ORGANIZER, ADMIN)

    title = (title or "").strip()
    if not title:
        raise ValidationFailed("Title is required")
    try:
        rows, seats_per_row = int(rows), int(seats_per_row)
    except (TypeError, ValueError):
        raise ValidationFailed("Rows and seats per row must be numbers")
    if not 1 <= rows <= MAX_ROWS or not 1 <= seats_per_row <= MAX_SEATS_PER_ROW:
        raise ValidationFailed(f"Use 1-{MAX_ROWS} rows and 1-{MAX_SEATS_PER_ROW} seats per row")
    if starts_at is None or starts_at <= timezone.now():
        raise ValidationFailed("Start time must be in the future")

    with transaction.atomic():
        ev = query_one(
            "INSERT INTO events (organizer_id, title, description, venue, starts_at, status) "
            "VALUES (%s, %s, %s, %s, %s, 'PUBLISHED') RETURNING id",
            [user.id, title, (description or "").strip(), (venue or "").strip(), starts_at])
        query(
            "INSERT INTO seats (event_id, row_label, seat_number) "
            "SELECT %s, chr(64 + r), s FROM generate_series(1, %s) AS r, generate_series(1, %s) AS s",
            [ev["id"], rows, seats_per_row])
        writeAudit(user, "EVENT_UPDATED", event_id=ev["id"],
                   details={"created": True, "rows": rows, "seats_per_row": seats_per_row})
    return {"event_id": ev["id"]}
