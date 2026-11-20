from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from bookings import services as booking_services
from config.errors import NotFound


def my_bookings_view(request):
    return render(request, "bookings/my_bookings.html", {
        "bookings": booking_services.listMyBookings(request.user),
    })


def booking_confirmation_view(request, booking_id):
    booking = next((b for b in booking_services.listMyBookings(request.user)
                    if b["id"] == booking_id), None)
    if booking is None:
        raise NotFound("Booking not found")
    return render(request, "bookings/booking_confirmation.html", {"booking": booking})


@require_POST
def cancel_booking_view(request, booking_id):
    booking_services.cancelBooking(request.user, booking_id)
    messages.success(request, "Booking cancelled. Your seats are available again.")
    return redirect("/my/bookings/")