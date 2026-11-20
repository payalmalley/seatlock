from collections import OrderedDict
from datetime import datetime

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import ADMIN, ORGANIZER, require_role
from bookings import services as booking_services
from config.errors import ValidationFailed
from events.creation import createEvent
from events.services import listEvents


def event_list_view(request):
    return render(request, "events/event_list.html", {"events": listEvents(request.user)})


@require_http_methods(["GET", "POST"])
def event_create_view(request):
    require_role(request.user, ADMIN, ORGANIZER)   # students get a 403

    if request.method == "GET":
        return render(request, "events/event_form.html", {"form": {"rows": 6, "seats_per_row": 10}})

    form = {k: request.POST.get(k, "") for k in
            ("title", "description", "venue", "starts_at", "rows", "seats_per_row")}
    try:
        try:
            naive = datetime.strptime(form["starts_at"], "%Y-%m-%dT%H:%M")
        except ValueError:
            raise ValidationFailed("Please pick a valid start date and time")
        result = createEvent(
            request.user, form["title"], form["description"], form["venue"],
            timezone.make_aware(naive), form["rows"], form["seats_per_row"])
    except ValidationFailed as e:
        # Show the error on the form and keep what the user typed.
        return render(request, "events/event_form.html", {"form": form, "error": e.message})

    messages.success(request, "Event created and published.")
    return redirect(f"/events/{result['event_id']}/")


def seat_map_view(request, event_id):
    data = booking_services.getSeatMap(request.user, event_id)
    seats = data["seats"]

    rows = OrderedDict()
    for s in seats:
        rows.setdefault(s["row_label"], []).append(s)

    my_hold = [s for s in seats if s["mine"] and s["state"] == "HELD"]
    stats = {
        "available": sum(1 for s in seats if s["state"] == "AVAILABLE"),
        "booked": sum(1 for s in seats if s["state"] == "BOOKED"),
        "total": len(seats),
    }
    return render(request, "events/seat_map.html", {
        "event": data["event"],
        "seats": seats,
        "rows": [{"label": label, "seats": row_seats} for label, row_seats in rows.items()],
        "my_hold": my_hold,
        "my_hold_expires": my_hold[0]["hold_expires_at"] if my_hold else None,
        "stats": stats,
    })


@require_POST
def hold_view(request, event_id):
    # Service errors (conflict, expired, forbidden...) are handled by RBACMiddleware.process_exception
    booking_services.holdSeats(request.user, event_id, request.POST.getlist("seat_ids"))
    messages.success(request, "Seats held for 5 minutes. Confirm your booking before the timer runs out.")
    return redirect(f"/events/{event_id}/")


@require_POST
def confirm_view(request, event_id):
    result = booking_services.confirmHold(request.user, event_id)
    messages.success(request, "Booking confirmed!")
    return redirect(f"/my/bookings/{result['booking_id']}/")