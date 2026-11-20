from django.http import JsonResponse
from django.urls import path

from accounts import views as account_views
from bookings import views as booking_views
from config.db import query_one
from events import views as event_views


def health(request):
    query_one("SELECT 1 AS ok")
    return JsonResponse({"ok": True})


urlpatterns = [
    path("", account_views.dashboard_view),
    path("login/", account_views.login_view),
    path("logout/", account_views.logout_view),

    path("events/", event_views.event_list_view),
    path("events/new/", event_views.event_create_view),
    path("events/<int:event_id>/", event_views.seat_map_view),
    path("events/<int:event_id>/hold/", event_views.hold_view),
    path("events/<int:event_id>/confirm/", event_views.confirm_view),

    path("my/bookings/", booking_views.my_bookings_view),
    path("my/bookings/<int:booking_id>/", booking_views.booking_confirmation_view),
    path("my/bookings/<int:booking_id>/cancel/", booking_views.cancel_booking_view),

    path("health/", health),
]