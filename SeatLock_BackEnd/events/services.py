from django.db import transaction

from accounts.permissions import ADMIN, ORGANIZER, require_event_access, require_role
from audit.services import writeAudit
from bookings.locking import lock_seats, translate_db_errors
from config.db import query, query_one
from config.errors import Conflict, NotFound, ValidationFailed

EDITABLE_FIELDS = {"title", "description", "starts_at"}   # whitelist = safe to put in SQL


def _get_event(event_id, lock=False):
    ev = query_one(
        "SELECT id, organizer_id, version FROM events WHERE id = %s" + (" FOR UPDATE" if lock else ""),
        [event_id])
    if not ev:
        raise NotFound("Event not found")
    return ev


@translate_db_errors
def updateEvent(user, event_id, expected_version, changes):
    """Optimistic locking: update only if the version the user saw is still current."""
    require_role(user, ORGANIZER, ADMIN)
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown or not changes:
        raise ValidationFailed("Invalid fields", fields=sorted(unknown))
    with transaction.atomic():
        ev = _get_event(event_id, lock=True)
        require_event_access(user, ev)
        if ev["version"] != int(expected_version):
            raise Conflict("Event was changed by someone else, reload and retry",
                           current_version=ev["version"])
        sets = ", ".join(f"{k} = %s" for k in changes)
        row = query_one(
            f"UPDATE events SET {sets}, version = version + 1 WHERE id = %s AND version = %s RETURNING version",
            list(changes.values()) + [event_id, expected_version])
        if not row:
            raise Conflict("Event was changed by someone else")
        writeAudit(user, "EVENT_UPDATED", event_id=event_id, details={"changed": sorted(changes)})
    return {"version": row["version"]}


@translate_db_errors
def blockSeats(user, event_id, seat_ids):
    require_role(user, ORGANIZER, ADMIN)
    ids = sorted({int(s) for s in seat_ids})
    if not ids:
        raise ValidationFailed("No seats selected")
    with transaction.atomic():
        require_event_access(user, _get_event(event_id))
        lock_seats(event_id, ids)
        busy = query(
            "SELECT seat_id FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id "
            "WHERE b.status = 'CONFIRMED' AND bs.seat_id = ANY(%s) "
            "UNION SELECT seat_id FROM holds WHERE seat_id = ANY(%s) AND expires_at > now()",
            [ids, ids])
        if busy:   # organizers cannot block booked (or currently held) seats
            raise Conflict("Some seats are booked or held",
                           unavailable=[r["seat_id"] for r in busy])
        query("UPDATE seats SET status = 'BLOCKED' WHERE id = ANY(%s)", [ids])
        writeAudit(user, "EVENT_UPDATED", event_id=event_id, details={"blocked_seats": ids})
    return {"blocked": ids}


def listEventBookings(user, event_id):
    require_role(user, ORGANIZER, ADMIN)
    require_event_access(user, _get_event(event_id))
    return query(
        """
        SELECT b.id, b.status, b.checked_in_at, u.name, u.email,
               array_agg(s.label ORDER BY s.id) FILTER (WHERE s.id IS NOT NULL) AS seats
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        LEFT JOIN booking_seats bs ON bs.booking_id = b.id
        LEFT JOIN seats s ON s.id = bs.seat_id
        WHERE b.event_id = %s
        GROUP BY b.id, u.name, u.email
        ORDER BY b.id
        """,
        [event_id],
    )


@translate_db_errors
def checkIn(user, booking_id):
    require_role(user, ORGANIZER, ADMIN)
    with transaction.atomic():
        b = query_one(
            "SELECT b.id, b.event_id, b.status, b.checked_in_at, e.organizer_id "
            "FROM bookings b JOIN events e ON e.id = b.event_id WHERE b.id = %s FOR UPDATE OF b",
            [booking_id])
        if not b:
            raise NotFound("Booking not found")
        require_event_access(user, b)
        if b["status"] != "CONFIRMED":
            raise Conflict("Only confirmed bookings can be checked in")
        if b["checked_in_at"] is not None:
            raise Conflict("Already checked in")
        query("UPDATE bookings SET checked_in_at = now() WHERE id = %s", [booking_id])
        writeAudit(user, "CHECKIN", event_id=b["event_id"], details={"booking_id": booking_id})
    return {"booking_id": booking_id}