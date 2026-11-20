from django.contrib.auth.hashers import check_password
from django.db import transaction

from accounts.permissions import CurrentUser
from audit.services import writeAudit
from config.db import query_one


def _to_user(row):
    return CurrentUser(row["id"], row["email"], row["name"], row["role"].upper())


def load_user(user_id):
    row = query_one(
        "SELECT id, email, full_name AS name, role FROM users WHERE id = %s AND is_active",
        [user_id])
    return _to_user(row) if row else None


def authenticate(email, password):
    row = query_one(
        "SELECT id, email, full_name AS name, role, password_hash FROM users "
        "WHERE lower(email) = lower(%s) AND is_active",
        [email or ""])
    ok = bool(row) and check_password(password or "", row["password_hash"])
    with transaction.atomic():
        if ok:
            writeAudit(None, "LOGIN", actor_id=row["id"])
        else:
            writeAudit(None, "LOGIN_FAILED", details={"email": email})
    return _to_user(row) if ok else None