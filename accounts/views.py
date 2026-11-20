from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from accounts.services import authenticate


def _safe_next(request, value):
    """Only follow local paths, so ?next= can't redirect to another site."""
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}):
        return value
    return "/"


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user is not None:
        return redirect("/")

    if request.method == "GET":
        return render(request, "login.html", {"next": request.GET.get("next", "")})

    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    next_url = request.POST.get("next", "")

    user = authenticate(email, password)
    if user is None:
        return render(request, "login.html", {
            "error": "Invalid email or password.",
            "email": email,
            "next": next_url,
        })

    request.session.cycle_key()  # new session key on login
    request.session["uid"] = user.id
    return redirect(_safe_next(request, next_url))


@require_POST
def logout_view(request):
    request.session.flush()
    return redirect("/login/")


def dashboard_view(request):
    return redirect("/events/")