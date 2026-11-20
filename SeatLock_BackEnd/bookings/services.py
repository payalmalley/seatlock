from collections import defaultdict

from django.db import transaction

from accounts.permissions import ADMIN, ORGANIZER, STUDENT, require_event_access, require_role
from audit.services import writeAudit
from bookings.locking import lock_seats, translate_db_errors
from config.db import query, query_one
from config.errors import Conflict, Forbidden, HoldExpired, NotFound, ValidationFailed

MAX_SEATS = 4


def _clean_seat_ids(seat_ids):
    try:
        ids = sorted({int(s) for s in seat_ids})
    except (TypeError, ValueError):
        raise ValidationFailed("Invalid seat ids")
    if not 1 <= len(ids) <= MAX_SEATS:
        raise ValidationFailed("Choose between 1 and 4 seats")
    return ids


def _open_event(event_id):
    """Event must be published and not started yet (booking closes at start time)."""
    ev = query_one(
        "SELECT id, status, (starts_at > now()) AS is_open FROM events WHERE id = %s", [event_id]
    )
    if not ev or ev["status"].upper() != "PUBLISHED":
        raise NotFound("Event not found")
    if not ev["is_open"]:
        raise Conflict("Booking is closed for this event")
    return ev


def _expire_holds(event_id):
    """Release expired holds and log HOLD_EXPIRED. Call inside a transaction."""
    rows = query(
        "DELETE FROM holds WHERE event_id = %s AND expires_at <= now() RETURNING user_id, seat_id",
        [event_id],
    )
    by_user = defaultdict(list)
    for r in rows:
        by_user[r["user_id"]].append(r["seat_id"])
    for uid, seats in by_user.items():
        writeAudit(None, "HOLD_EXPIRED", event_id=event_id, actor_id=uid, details={"seats": seats})


# ---------------------------------------------------------------- getSeatMap
def getSeatMap(user, event_id):
    require_role(user, ADMIN, ORGANIZER, STUDENT)
    ev = query_one(
        "SELECT id, organizer_id, title, status, starts_at, version, (starts_at > now()) AS is_open "
        "FROM events WHERE id = %s", [event_id])
    if not ev or (user.role == STUDENT and ev["status"].upper() != "PUBLISHED"):
        raise NotFound("Event not found")
    if user.role == ORGANIZER:
        require_event_access(user, ev)

    seats = query(
        """
        SELECT s.id, s.label,
               CASE WHEN s.status = 'BLOCKED' THEN 'BLOCKED'
                    WHEN bk.seat_id IS NOT NULL THEN 'BOOKED'
                    WHEN h.seat_id IS NOT NULL THEN 'HELD'
                    ELSE 'AVAILABLE' END AS state,
               (h.user_id = %s) AS mine,
               CASE WHEN h.user_id = %s THEN h.expires_at END AS hold_expires_at
        FROM seats s
        LEFT JOIN (SELECT bs.seat_id FROM booking_seats bs
                   JOIN bookings b ON b.id = bs.booking_id
                   WHERE b.status = 'CONFIRMED' AND b.event_id = %s) bk ON bk.seat_id = s.id
        LEFT JOIN holds h ON h.seat_id = s.id AND h.expires_at > now()
        WHERE s.event_id = %s
        ORDER BY s.id
        """,
        [user.id, user.id, event_id, event_id],
    )
    return {"event": ev, "seats": seats}


# ----------------------------------------------------------------- holdSeats
def _hold_in_tx(user, event_id, ids):
    _open_event(event_id)
    seats = lock_seats(event_id, ids)       # serialization point, stable order
    _expire_holds(event_id)                 # expiry check inside the transaction

    unavailable = [{"seat_id": s["id"], "reason": "BLOCKED"} for s in seats
                   if s["status"].upper() == "BLOCKED"]
    for r in query(
        "SELECT bs.seat_id FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id "
        "WHERE b.status = 'CONFIRMED' AND bs.seat_id = ANY(%s)", [ids]):
        unavailable.append({"seat_id": r["seat_id"], "reason": "BOOKED"})
    for r in query(
        "SELECT seat_id FROM holds WHERE seat_id = ANY(%s) AND user_id <> %s AND expires_at > now()",
        [ids, user.id]):
        unavailable.append({"seat_id": r["seat_id"], "reason": "HELD"})
    if unavailable:                          # all-or-nothing
        raise Conflict("Some seats are unavailable", unavailable=unavailable)

    owned = query_one(
        "SELECT count(*) AS n FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id "
        "WHERE b.user_id = %s AND b.event_id = %s AND b.status = 'CONFIRMED'",
        [user.id, event_id])["n"]
    if owned + len(ids) > MAX_SEATS:
        raise Conflict(f"Limit is {MAX_SEATS} seats per event (you already own {owned})",
                       owned=owned)

    query("DELETE FROM holds WHERE event_id = %s AND user_id = %s", [event_id, user.id])  # replace old hold
    held = query(
        "INSERT INTO holds (event_id, seat_id, user_id, expires_at) "
        "SELECT %s, s, %s, now() + interval '5 minutes' FROM unnest(%s::bigint[]) AS s "
        "RETURNING seat_id, expires_at",
        [event_id, user.id, ids],
    )
    writeAudit(user, "SEAT_HELD", event_id=event_id, details={"seats": ids})
    return {"seat_ids": ids, "expires_at": held[0]["expires_at"]}


@translate_db_errors
def holdSeats(user, event_id, seat_ids):
    require_role(user, STUDENT)
    ids = _clean_seat_ids(seat_ids)
    try:
        with transaction.atomic():
            return _hold_in_tx(user, event_id, ids)
    except Conflict as e:
        # The hold rolled back, so log the rejection in its own transaction.
        with transaction.atomic():
            writeAudit(user, "SEAT_HOLD_REJECTED", event_id=event_id,
                       details={"seats": ids, "reason": e.message, **e.extra})
        raise


# --------------------------------------------------------------- confirmHold
def _confirm_in_tx(user, event_id):
    _open_event(event_id)
    mine = query("SELECT seat_id FROM holds WHERE event_id = %s AND user_id = %s", [event_id, user.id])
    if not mine:
        raise HoldExpired("You have no active hold (it may have expired)")
    ids = sorted(r["seat_id"] for r in mine)
    lock_seats(event_id, ids)
    live = query(
        "SELECT seat_id FROM holds WHERE event_id = %s AND user_id = %s AND expires_at > now() FOR UPDATE",
        [event_id, user.id])
    if len(live) != len(ids):
        raise HoldExpired("Your hold expired")

    owned = query_one(
        "SELECT count(*) AS n FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id "
        "WHERE b.user_id = %s AND b.event_id = %s AND b.status = 'CONFIRMED'",
        [user.id, event_id])["n"]
    if owned + len(ids) > MAX_SEATS:
        raise Conflict("Limit is 4 seats per event")

    booking = query_one(
        "INSERT INTO bookings (event_id, user_id, status) VALUES (%s, %s, 'CONFIRMED') RETURNING id",
        [event_id, user.id])
    query("INSERT INTO booking_seats (booking_id, seat_id) SELECT %s, s FROM unnest(%s::bigint[]) AS s",
          [booking["id"], ids])
    query("DELETE FROM holds WHERE event_id = %s AND user_id = %s", [event_id, user.id])
    writeAudit(user, "BOOKING_CONFIRMED", event_id=event_id,
               details={"booking_id": booking["id"], "seats": ids})
    return {"booking_id": booking["id"], "seat_ids": ids}


@translate_db_errors
def confirmHold(user, event_id):
    require_role(user, STUDENT)
    try:
        with transaction.atomic():
            return _confirm_in_tx(user, event_id)
    except HoldExpired:
        with transaction.atomic():
            _expire_holds(event_id)         # release + HOLD_EXPIRED audit
        raise


# ------------------------------------------------------------- cancelBooking
@translate_db_errors
def cancelBooking(user, booking_id):
    require_role(user, STUDENT)
    with transaction.atomic():
        b = query_one(
            "SELECT id, event_id, user_id, status FROM bookings WHERE id = %s FOR UPDATE", [booking_id])
        if not b:
            raise NotFound("Booking not found")
        if b["user_id"] != user.id:
            raise Forbidden("You can only cancel your own bookings")
        if b["status"] != "CONFIRMED":
            raise Conflict("Booking is already cancelled")
        seats = query("DELETE FROM booking_seats WHERE booking_id = %s RETURNING seat_id", [booking_id])
        query("UPDATE bookings SET status = 'CANCELLED' WHERE id = %s", [booking_id])
        writeAudit(user, "BOOKING_CANCELLED", event_id=b["event_id"],
                   details={"booking_id": booking_id, "seats": [s["seat_id"] for s in seats]})
    return {"booking_id": booking_id}


# ------------------------------------------------------------- listMyBookings
def listMyBookings(user):
    require_role(user, STUDENT)
    return query(
        """
        SELECT b.id, b.event_id, e.title, b.status, b.created_at,
               array_agg(s.label ORDER BY s.id) FILTER (WHERE s.id IS NOT NULL) AS seats
        FROM bookings b
        JOIN events e ON e.id = b.event_id
        LEFT JOIN booking_seats bs ON bs.booking_id = b.id
        LEFT JOIN seats s ON s.id = bs.seat_id
        WHERE b.user_id = %s
        GROUP BY b.id, e.title
        ORDER BY b.created_at DESC
        """,
        [user.id],
    )