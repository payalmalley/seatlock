from dataclasses import dataclass

from config.errors import Forbidden

ADMIN, ORGANIZER, STUDENT = "ADMIN", "ORGANIZER", "STUDENT"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    name: str
    role: str

    @property
    def full_name(self):
        return self.name


def require_role(user, *roles):
    """Service-level check #2 (route middleware is check #1)."""
    if user is None or user.role not in roles:
        raise Forbidden("You do not have permission for this action")


def require_event_access(user, event):
    """Admin: any event. Organizer: only own events. `event` needs organizer_id."""
    if user.role == ADMIN:
        return
    if user.role == ORGANIZER and event["organizer_id"] == user.id:
        return
    raise Forbidden("You can only access your own events")