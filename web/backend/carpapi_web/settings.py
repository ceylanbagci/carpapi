"""Django settings for the carpapi_web project.

Reads DB connection info and HTTP host from environment variables so the
same settings file works on the dev box, on the LAN host, and in CI.
A sensible default points at the canonical local Postgres on port 5433.
"""
from __future__ import annotations

import os
from datetime import timedelta
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
        # Default list covers local dev + the App Runner internal
        # hostname + the custom domain (carpappi.com). App Runner sets
        # the Host header to the public hostname, so api.carpappi.com
        # must be included once the custom domain is active.
        "localhost,127.0.0.1,0.0.0.0,api.carpappi.com,"
        "gt3mapscrz.us-east-1.awsapprunner.com,*",
    ).split(",")
    if h.strip()
]

# Used by allauth for absolute URLs in confirmation emails and OAuth
# redirect callbacks. Override per deploy via DJANGO_SITE_DOMAIN.
# Default is now the custom domain so confirmation links point at
# api.carpappi.com — fall back to the App Runner hostname via env.
SITE_ID = 1
DJANGO_SITE_DOMAIN = os.environ.get(
    "DJANGO_SITE_DOMAIN", "api.carpappi.com"
)


INSTALLED_APPS = [
    # Django built-ins (admin needs auth + contenttypes + sessions +
    # messages + staticfiles in INSTALLED_APPS to render).
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    # allauth: account = email/password, socialaccount = OAuth,
    # provider modules (`google`) enable specific providers.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    "phonenumber_field",
    # Our apps
    "accounts",
    "api",
]

# Order matters. WhiteNoise must come right after SecurityMiddleware so
# it intercepts static-file requests before any other middleware can
# touch them. allauth.account.middleware.AccountMiddleware is required
# by allauth >= 0.56.
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "carpapi_web.urls"

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
            ],
        },
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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files served by WhiteNoise in production. collectstatic puts
# everything (admin CSS, DRF browsable-API CSS, anything we add) under
# STATIC_ROOT; WhiteNoise serves them from there with long-cache
# headers and gzip/brotli compression.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────────────────────────── #
# Custom user model
# ──────────────────────────────────────────────────────────────────── #
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    # Falls back to Django's default for admin login, then allauth's
    # backend for /accounts/login/ + Google.
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# ──────────────────────────────────────────────────────────────────── #
# REST Framework
# ──────────────────────────────────────────────────────────────────── #
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "dj_rest_auth.jwt_auth.JWTCookieAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
}

# JWT settings for dj-rest-auth.
#
# Bearer-only — no cookies. The SPA on CloudFront stores the
# access/refresh tokens in localStorage and sends them as
# `Authorization: Bearer <jwt>` on each request. Avoids the
# cross-site-cookie + Secure + SameSite=None complexity, and works
# identically for mobile clients later.
REST_AUTH = {
    "USE_JWT": True,
    "JWT_AUTH_COOKIE": None,
    "JWT_AUTH_REFRESH_COOKIE": None,
    "JWT_AUTH_HTTPONLY": False,
    "SESSION_LOGIN": False,
    "REGISTER_SERIALIZER": "accounts.serializers.CarPapiRegisterSerializer",
    "USER_DETAILS_SERIALIZER": "accounts.serializers.CarPapiUserSerializer",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ──────────────────────────────────────────────────────────────────── #
# allauth (email + Google OAuth)
# ──────────────────────────────────────────────────────────────────── #
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = os.environ.get(
    "ACCOUNT_EMAIL_VERIFICATION", "optional"
)  # "mandatory" once email infra is ready
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"  # provider already verified
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_QUERY_EMAIL = True

# Google OAuth — set DJANGO_GOOGLE_CLIENT_ID + DJANGO_GOOGLE_CLIENT_SECRET
# env vars on App Runner (or in .env locally). Without them the provider
# is configured but won't accept logins. Add the redirect URI
#   https://<service>.awsapprunner.com/accounts/google/login/callback/
# to your Google Cloud Console OAuth client.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.environ.get("DJANGO_GOOGLE_CLIENT_ID", ""),
            "secret": os.environ.get("DJANGO_GOOGLE_CLIENT_SECRET", ""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online", "prompt": "select_account"},
        "OAUTH_PKCE_ENABLED": True,
        "FETCH_USERINFO": True,
    },
}

LOGIN_REDIRECT_URL = "/api/auth/user/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_ON_GET = True  # so the React frontend can hit a simple GET

# ──────────────────────────────────────────────────────────────────── #
# Email (console for dev, SES via env in prod)
# ──────────────────────────────────────────────────────────────────── #
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "CarPapi <noreply@carpapi.test>"
)
# SES envelope when EMAIL_BACKEND is set to django_ses.SESBackend:
AWS_SES_REGION_NAME = os.environ.get("AWS_REGION", "us-east-1")
AWS_SES_REGION_ENDPOINT = f"email.{AWS_SES_REGION_NAME}.amazonaws.com"

# ──────────────────────────────────────────────────────────────────── #
# Admin OTP (step-up auth for is_staff users)
#
# When a staff user logs in via /api/auth/login-step-up/, the API
# returns a challenge instead of a JWT. The challenge code is
# delivered via Twilio (if creds are set) or email (otherwise).
# See accounts/otp.py for the full delivery chain.
# ──────────────────────────────────────────────────────────────────── #
# Toggle to disable the staff step-up entirely (local dev / CI). When
# false, /api/auth/login-step-up/ issues JWTs to staff users without
# the OTP detour. Default true so production behavior is unchanged.
ADMIN_OTP_ENABLED = os.environ.get("ADMIN_OTP_ENABLED", "true").lower() in (
    "1", "true", "yes",
)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
# Prefer a Messaging Service SID (MG...) over a single From number.
# Messaging Services handle multi-region pools + carrier compliance
# automatically. Set either one — the OTP sender uses the SID first.
TWILIO_MESSAGING_SERVICE_SID = os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

# WhatsApp Cloud API (Meta) — preferred OTP delivery channel.
# Requires a pre-approved "Authentication" message template in
# WhatsApp Business Manager. See accounts/otp.py for the wire format.
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TEMPLATE_NAME = os.environ.get(
    "WHATSAPP_TEMPLATE_NAME", "otp_authentication"
)
WHATSAPP_TEMPLATE_LANGUAGE = os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
# Shared secret echoed back to Meta during webhook verification.
# Pick any opaque string; paste the same value into Meta's App
# Dashboard → WhatsApp → Configuration → "Verify token".
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.environ.get(
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN", ""
)
# Optional comma-separated allow-list. When non-empty, OTP via SMS
# only attempts delivery to numbers on this list (the user's stored
# `phone` must match). Useful for single-admin MVPs.
ADMIN_ALLOWED_PHONES = [
    p.strip()
    for p in os.environ.get("ADMIN_ALLOWED_PHONES", "+12019376526").split(",")
    if p.strip()
]

# ──────────────────────────────────────────────────────────────────── #
# CORS (cross-origin between CloudFront frontend and App Runner API)
# ──────────────────────────────────────────────────────────────────── #
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost(:\d+)?$",
    r"^http://127\.0\.0\.1(:\d+)?$",
    r"^http://192\.168\.\d+\.\d+(:\d+)?$",
    r"^http://10\.\d+\.\d+\.\d+(:\d+)?$",
    # Production frontend on CloudFront (S3-backed React SPA).
    r"^https://[a-z0-9]+\.cloudfront\.net$",
    # Production custom domain (carpappi.com — note the two p's).
    # Covers apex + www both serving the SPA.
    r"^https://(www\.)?carpappi\.com$",
]

# Extra explicit allow-list pulled from env so a new deploy can add a
# custom domain without a code change. Comma-separated.
_extra = [
    o.strip()
    for o in os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOWED_ORIGINS = _extra
CORS_ALLOW_CREDENTIALS = True  # so JWT cookies travel cross-site

from corsheaders.defaults import default_headers as _default_cors_headers
CORS_ALLOW_HEADERS = list(_default_cors_headers) + ["x-carpapi-auth"]

# Trust the App Runner / CloudFront proxies for CSRF + secure cookies.
CSRF_TRUSTED_ORIGINS = [
    "https://*.awsapprunner.com",
    "https://*.cloudfront.net",
    # Custom domain — apex + www (frontend) and api subdomain (backend).
    "https://carpappi.com",
    "https://www.carpappi.com",
    "https://api.carpappi.com",
]

# ──────────────────────────────────────────────────────────────────── #
# Other
# ──────────────────────────────────────────────────────────────────── #
# Shared-passphrase auth for /api/chat/ (see web/backend/api/views.py).
CARPAPI_API_KEY = os.environ.get("CARPAPI_API_KEY", "")
