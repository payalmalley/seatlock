import logging

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

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


def _deny(request, reason):
    match = getattr(request, "resolver_match", None)
    event_id = match.kwargs.get("event_id") if match else None
    try:
        with transaction.atomic():
            writeAudit(request.user, "ACCESS_DENIED", event_id=event_id,
                       details={"path": request.path, "method": request.method, "reason": reason})
    except Exception:
        log.exception("Could not write ACCESS_DENIED audit")
    return HttpResponse(f"403 Forbidden: {reason}", status=403)


class RBACMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(PUBLIC_PREFIXES):
            return self.get_response(request)
        if request.user is None:
            return redirect(f"/login/?next={path}")
        for prefix, roles in ROLE_RULES:
            if path.startswith(prefix) and request.user.role not in roles:
                return _deny(request, "Role not allowed for this route")
        return self.get_response(request)

    def process_exception(self, request, exc):
        # Maps service errors to HTTP codes: 403 (+audit), 404, 409, 503 ...
        if isinstance(exc, AuthRequired):
            return redirect("/login/")
        if isinstance(exc, Forbidden):
            return _deny(request, exc.message)
        if isinstance(exc, AppError):
            return JsonResponse({"error": exc.message, **exc.extra}, status=exc.status)
        return None