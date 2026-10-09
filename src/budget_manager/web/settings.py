"""Django settings. Everything is stored in one data directory on the machine running the app.

Environment variables:

- ``BUDGET_DATA_DIR``: where the database and secret key live (default: ``./data``).
- ``BUDGET_ALLOWED_NETWORKS``: comma-separated networks allowed to connect
  (default: loopback, private LAN ranges and Tailscale's 100.64.0.0/10; Tailscale's IPv6
  addresses are inside fc00::/7).
- ``BUDGET_ALLOWED_HOSTS``: comma-separated host names (default: ``*``; the network check
  above is what keeps the app off the internet).
- ``BUDGET_DEBUG``: set to ``1`` during development.
- ``BUDGET_UPDATER``: set to ``1`` by the Windows launcher, which updates and restarts the app
  when the *Update now* button in Settings asks for it.
- ``BUDGET_CHECK_MINUTES``: how often the Windows launcher checks for a new version (0: never).
- ``BUDGET_COMMIT``: the commit the app runs, shown in Settings next to the version (set by
  the Windows launcher).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from budget_manager import __version__

PACKAGE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BUDGET_DATA_DIR", Path.cwd() / "data")).resolve()


def _secret_key() -> str:
    if key := os.environ.get("BUDGET_SECRET_KEY"):
        return key
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(50))
        path.chmod(0o600)
    return path.read_text().strip()


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = _secret_key()
DEBUG = os.environ.get("BUDGET_DEBUG") == "1"

# The Windows launcher watches for this file and then updates to the newest version and
# restarts the app (scripts/windows/run-budget.ps1).
UPDATER = os.environ.get("BUDGET_UPDATER") == "1"
UPDATE_REQUEST_FILE = DATA_DIR / "update.request"
CHECK_MINUTES = int(os.environ.get("BUDGET_CHECK_MINUTES") or 0)
VERSION = __version__
COMMIT = os.environ.get("BUDGET_COMMIT", "")
ALLOWED_HOSTS = _list("BUDGET_ALLOWED_HOSTS", "*")
ALLOWED_NETWORKS = _list(
    "BUDGET_ALLOWED_NETWORKS",
    "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,169.254.0.0/16,100.64.0.0/10,"
    "::1/128,fc00::/7,fe80::/10",
)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "budget_manager.ledger",
]

MIDDLEWARE = [
    "budget_manager.web.middleware.LocalNetworkOnlyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "budget_manager.ledger.scope.BudgetMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "budget_manager.web.urls"
WSGI_APPLICATION = "budget_manager.web.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "budget_manager.ledger.context_processors.navigation",
            ],
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "budget.sqlite3",
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# Paths, not URL names: inside a budget every reversed name gets the budget's prefix.
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/Copenhagen"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"  # absolute, so it is not put under a budget's prefix
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
