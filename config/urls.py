from django.http import JsonResponse
from django.urls import path

from accounts import views as account_views
from config.db import query_one


def health(request):
    query_one("SELECT 1 AS ok")
    return JsonResponse({"ok": True})


urlpatterns = [
    path("", account_views.dashboard_view),
    path("login/", account_views.login_view),
    path("logout/", account_views.logout_view),
    path("health/", health),
]