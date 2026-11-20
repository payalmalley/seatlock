def current_user(request):
    return {"current_user": getattr(request, "user", None)}