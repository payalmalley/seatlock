import logging
from urllib.parse import quote

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.permissions import ADMIN, ORGANIZER, STUDENT
from accounts.services import load_user
from audit.services import writeAudit
from config.errors import AppError, AuthRequired, Forbidden

log = logging.getLogger(__name__)

PUBLIC_PREFIXES = ("/login/", "/health/", "/static/")
# Route-level RBAC (check #1). Other URLs only need a logged-in user.
ROLE_RULES = [
    ("/manage/", {ADMIN}),
    ("/organizer/", {ORGANIZER, ADMIN}),
    ("/my/", {STUDENT}),
]


class AuthMiddleware:
    """Loads request.user from the DB on every request, so role changes apply immediately."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        uid = request.session.get("uid")
        request.user = load_user(uid) if uid else None
        return self.get_response(request)


def _audit_denied(request, reason):
    match = getattr(request, "resolver_match", None)
    event_id = match.kwargs.get("event_id") if match else None
    try:
        with transaction.atomic():
            writeAudit(request.user, "ACCESS_DENIED", event_id=event_id,
                       details={"path": request.path, "method": request.method, "reason": reason})
    except Exception:
        log.exception("Could not write ACCESS_DENIED audit")


def _wants_json(request):
    return (request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", ""))


def _deny(request, reason):
    _audit_denied(request, reason)
    if _wants_json(request):
        return JsonResponse({"error": reason}, status=403)
    return HttpResponse(f"403 Forbidden: {reason}", status=403)


def _back(request):
    """Go back to the page the form was on; only ever to our own site."""
    ref = request.META.get("HTTP_REFERER", "")
    if ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()}):
        return ref
    return "/events/"


def _status_of(exc):
    for attr in ("status", "status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return 500


def _message_of(exc):
    return getattr(exc, "message", None) or str(exc) or "Something went wrong."


class RBACMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(PUBLIC_PREFIXES):
            return self.get_response(request)
        if request.user is None:
            return redirect(f"/login/?next={quote(path)}")
        for prefix, roles in ROLE_RULES:
            if path.startswith(prefix) and request.user.role not in roles:
                return _deny(request, "Role not allowed for this route")
        return self.get_response(request)

    def process_exception(self, request, exc):
        # Maps service errors (AppError subclasses) to a response.
        # Anything else returns None, so Django shows its normal 500 page.
        if not isinstance(exc, (AppError, AuthRequired, Forbidden)):
            return None

        status = _status_of(exc)
        message = _message_of(exc)

        # 401: not logged in
        if isinstance(exc, AuthRequired) or status == 401:
            if _wants_json(request):
                return JsonResponse({"error": message}, status=401)
            return redirect(f"/login/?next={quote(request.path)}")

        # 403: logged in but not allowed (also written to the audit log)
        if isinstance(exc, Forbidden) or status == 403:
            return _deny(request, message)

        # Everything else: 400 / 404 / 409 / 503
        if _wants_json(request):
            return JsonResponse({"error": message}, status=status)

        messages.error(request, message)
        target = _back(request)
        # Avoid a redirect loop if the page we would return to is the one that failed.
        if target.split("?")[0].rstrip("/").endswith(request.path.rstrip("/")):
            target = "/events/"
        if request.path.rstrip("/") == "/events":
            return HttpResponse(message, status=status)
        return redirect(target)