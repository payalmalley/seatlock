from django.contrib.auth.hashers import check_password
from django.db import transaction

from accounts.permissions import CurrentUser
from audit.services import writeAudit
from config.db import query_one


def load_user(user_id):
    row = query_one("SELECT id, email, name, role FROM users WHERE id = %s", [user_id])
    if not row:
        return None
    return CurrentUser(row["id"], row["email"], row["name"], row["role"].upper())


def authenticate(email, password):
    row = query_one(
        "SELECT id, email, name, role, password_hash FROM users WHERE lower(email) = lower(%s)",
        [email or ""],
    )
    ok = bool(row) and check_password(password or "", row["password_hash"])
    with transaction.atomic():
        if ok:
            writeAudit(None, "LOGIN", actor_id=row["id"])
        else:
            writeAudit(None, "LOGIN_FAILED", details={"email": email})
    if not ok:
        return None
    return CurrentUser(row["id"], row["email"], row["name"], row["role"].upper())