import os
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # no-op inside Docker and on Vercel

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Needed when the site runs behind Vercel's HTTPS proxy (otherwise login POST fails CSRF).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"]
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# No models and no migrations: db/schema.sql is the single source of truth.
INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "accounts.middleware.AuthMiddleware",
    "accounts.middleware.RBACMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "SeatLock_FrontEnd" / "templates"],
    "APP_DIRS": False,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.messages.context_processors.messages",
            "config.context.current_user",
        ],
    },
}]


def _database():
    # Prefer a direct (non-pooled) URL: the lock_timeout option below is not accepted by poolers.
    url = (os.environ.get("DATABASE_URL_UNPOOLED")
           or os.environ.get("POSTGRES_URL_NON_POOLING")
           or os.environ.get("DATABASE_URL"))
    options = {"options": "-c lock_timeout=2000"}  # lock wait > 2s -> 503
    if url:
        u = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(u.query)
        options["sslmode"] = query.get("sslmode", ["require"])[0]
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": u.path.lstrip("/"),
            "USER": urllib.parse.unquote(u.username or ""),
            "PASSWORD": urllib.parse.unquote(u.password or ""),
            "HOST": u.hostname,
            "PORT": u.port or 5432,
            "ATOMIC_REQUESTS": False,
            "OPTIONS": options,
        }
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "seatlock"),
        "USER": os.environ.get("POSTGRES_USER", "seatlock"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "change_me"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "ATOMIC_REQUESTS": False,  # services open their own transaction.atomic()
        "OPTIONS": options,
    }


DATABASES = {"default": _database()}

# Signed-cookie sessions and messages, so no django_session table is needed.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "SeatLock_FrontEnd" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # Vercel runs collectstatic automatically when this is set

USE_TZ = True
TIME_ZONE = "Asia/Kolkata"  # event times typed in the form and shown on pages are India time
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"