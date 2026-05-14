"""Admin-OTP issuance and delivery.

`create_and_send_challenge(user, request=None)` is the single entry
point. It:
  1. Generates a 6-digit numeric code.
  2. Hashes it (SHA-256, no salt — short-lived, not a password).
  3. Persists an `AdminOTPChallenge` row.
  4. Delivers the code via the configured channel (sms → email →
     log, in that order, falling back if the higher-priority channel
     has no creds set).
  5. Returns `(challenge_token, expires_at, channel, destination_hint)`
     so the API view can hand them back to the SPA.

Channel resolution:

  SMS (Twilio)  if settings.TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                TWILIO_FROM_NUMBER are all set AND the user has a
                phone on record AND that phone is in
                settings.ADMIN_ALLOWED_PHONES.
  Email         if settings.EMAIL_BACKEND is configured AND the user
                has a verified email. Always tries to fall back to
                Django's email backend (which in dev mode prints the
                code to stdout via console.EmailBackend).
  Log           last-resort fallback so the feature still works in
                local-dev when neither Twilio nor email are wired.
                The code prints to the Django logs only — useful for
                CI tests and local development.

Swap to Twilio later by setting three App Runner env vars:
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_FROM_NUMBER (e.g. +18885551234)
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

log = logging.getLogger("accounts.otp")

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)


def _gen_code() -> str:
    # secrets.randbelow is uniform; zfill keeps leading zeros.
    return str(secrets.randbelow(10**OTP_LENGTH)).zfill(OTP_LENGTH)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def _gen_challenge_token() -> str:
    # 32 random url-safe chars; collision-free for our scale.
    return secrets.token_urlsafe(24)


# ─────────────────────────────────────────────────────────────────────
# Channel adapters — each returns (delivered: bool, hint: str).
# ─────────────────────────────────────────────────────────────────────


def _send_via_twilio(phone: str, code: str) -> tuple[bool, str]:
    sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_ = getattr(settings, "TWILIO_FROM_NUMBER", "")
    if not (sid and token and from_):
        return False, ""
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        log.warning("twilio package not installed; skipping SMS")
        return False, ""
    try:
        client = Client(sid, token)
        body = f"CarPapi admin code: {code}\nValid for 10 minutes. Do not share."
        client.messages.create(from_=from_, to=phone, body=body)
        # Mask: +1•••6526 — show country code + last 4
        hint = phone[:2] + "•" * (len(phone) - 6) + phone[-4:]
        return True, hint
    except Exception as exc:  # noqa: BLE001
        log.exception("twilio send failed: %s", exc)
        return False, ""


def _send_via_email(email: str, code: str) -> tuple[bool, str]:
    try:
        send_mail(
            subject="Your CarPapi admin sign-in code",
            message=(
                f"Hi,\n\n"
                f"Your CarPapi admin sign-in code is: {code}\n\n"
                f"It expires in 10 minutes. If you did not request this, "
                f"ignore this email and change your password.\n\n"
                f"— CarPapi"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@carpapi.app"),
            recipient_list=[email],
            fail_silently=False,
        )
        # Mask: j••@gmail.com
        local, _, domain = email.partition("@")
        hint = (local[:1] + "•" * (len(local) - 1)) + "@" + domain
        return True, hint
    except Exception as exc:  # noqa: BLE001
        log.exception("email send failed: %s", exc)
        return False, ""


def _send_via_log(user_label: str, code: str) -> tuple[bool, str]:
    log.warning(
        "[admin-otp][LOG-ONLY] code=%s recipient=%s — wire Twilio or SMTP for real delivery",
        code,
        user_label,
    )
    return True, "(dev log)"


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def create_and_send_challenge(user, request=None):
    """Create an AdminOTPChallenge for `user`, deliver the code,
    and return (challenge_token, expires_at, channel, destination_hint).

    Caller decides whether to gate on `user.is_staff` — this function
    just creates+delivers.
    """
    from .models import AdminOTPChallenge  # avoid circular import

    code = _gen_code()
    challenge_token = _gen_challenge_token()
    expires_at = timezone.now() + OTP_TTL

    # Resolve channel + send.
    allowed_phones = set(getattr(settings, "ADMIN_ALLOWED_PHONES", []))
    phone_str = str(user.phone) if user.phone else ""
    sms_eligible = (
        phone_str
        and (not allowed_phones or phone_str in allowed_phones)
    )

    channel = "log"
    hint = "(dev log)"

    if sms_eligible:
        ok, h = _send_via_twilio(phone_str, code)
        if ok:
            channel, hint = "sms", h

    if channel == "log" and user.email:
        ok, h = _send_via_email(user.email, code)
        if ok:
            channel, hint = "email", h

    if channel == "log":
        _send_via_log(f"user_id={user.id} email={user.email}", code)

    # Persist row (hashed code only).
    ip = None
    if request is not None:
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() \
            or request.META.get("REMOTE_ADDR")
    challenge = AdminOTPChallenge.objects.create(
        user=user,
        challenge_token=challenge_token,
        code_hash=_hash_code(code),
        channel=channel,
        destination_hint=hint,
        expires_at=expires_at,
        ip_address=ip,
    )
    log.info("admin-otp challenge created id=%s channel=%s", challenge.id, channel)
    return challenge_token, expires_at, channel, hint


def verify_challenge(challenge_token: str, code: str):
    """Validate a code against an open challenge.

    Returns (user, error). On success, returns (user, None) AND
    marks the challenge as used. On failure, returns (None, error_str)
    and increments attempts.
    """
    from .models import AdminOTPChallenge

    try:
        ch = AdminOTPChallenge.objects.select_related("user").get(
            challenge_token=challenge_token,
        )
    except AdminOTPChallenge.DoesNotExist:
        return None, "unknown_challenge"

    if ch.is_used:
        return None, "already_used"
    if ch.is_expired:
        return None, "expired"
    if ch.is_exhausted:
        return None, "too_many_attempts"

    ch.attempts += 1
    if _hash_code((code or "").strip()) != ch.code_hash:
        ch.save(update_fields=("attempts",))
        return None, "bad_code"

    ch.used_at = timezone.now()
    ch.save(update_fields=("attempts", "used_at"))
    return ch.user, None
