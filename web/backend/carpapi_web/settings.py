"""Django settings for the carpapi_web project.

Reads DB connection info and HTTP host from environment variables so the
same settings file works on the dev box, on the LAN host, and in CI.
A sensible default points at the canonical local Postgres on port 5433.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-not-for-production-replace-me-9f80136",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1,0.0.0.0,*",
    ).split(",")
    if h.strip()
]


INSTALLED_APPS = [
    "api",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "carpapi_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "carpapi_web.wsgi.application"
ASGI_APPLICATION = "carpapi_web.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("CARPAPI_DB_NAME", "carpapi"),
        "USER": os.environ.get("CARPAPI_DB_USER", "carpapi"),
        "PASSWORD": os.environ.get("CARPAPI_DB_PASSWORD", "carpapi"),
        "HOST": os.environ.get("CARPAPI_DB_HOST", "localhost"),
        "PORT": os.environ.get("CARPAPI_DB_PORT", "5433"),
        "OPTIONS": {"options": "-c search_path=public,ingest,monitor,ai"},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}


CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost(:\d+)?$",
    r"^http://127\.0\.0\.1(:\d+)?$",
    r"^http://192\.168\.\d+\.\d+(:\d+)?$",
    r"^http://10\.\d+\.\d+\.\d+(:\d+)?$",
    # Production frontend on CloudFront (S3-backed React SPA). Any
    # *.cloudfront.net subdomain matches — narrow this to the specific
    # distribution ID (e.g. ^https://d372ww3313y553\.cloudfront\.net$)
    # once you wire a custom domain.
    r"^https://[a-z0-9]+\.cloudfront\.net$",
]

# Extra explicit allow-list pulled from env so a new deploy can add a
# custom domain without a code change. Comma-separated.
import os as _os
_extra = [
    o.strip()
    for o in _os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOWED_ORIGINS = _extra

# Allow our custom auth header on cross-origin POSTs. Without this,
# browsers strip X-CarPapi-Auth from the preflight response and the
# real request goes out without the header → Django returns 401.
from corsheaders.defaults import default_headers as _default_cors_headers
CORS_ALLOW_HEADERS = list(_default_cors_headers) + ["x-carpapi-auth"]

# Shared-passphrase auth for /api/chat/ (see web/backend/api/views.py).
# Empty string disables the check — fine for local dev, bad in prod.
CARPAPI_API_KEY = _os.environ.get("CARPAPI_API_KEY", "")
