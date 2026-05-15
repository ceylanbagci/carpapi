"""Admin-OTP issuance and delivery.

`create_and_send_challenge(user, request=None)` is the single entry
point. It:
  1. Generates a 6-digit numeric code.
  2. Hashes it (SHA-256, no salt — short-lived, not a password).
  3. Persists an `AdminOTPChallenge` row.
  4. Delivers the code via the configured channel (WhatsApp → email →
     log, in that order, falling back if the higher-priority channel
     has no creds set).
  5. Returns `(challenge_token, expires_at, channel, destination_hint)`
     so the API view can hand them back to the SPA.

Channel resolution:

  WhatsApp     if settings.WHATSAPP_ACCESS_TOKEN +
               WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_TEMPLATE_NAME are
               set AND the user has a phone on record AND that phone
               is in settings.ADMIN_ALLOWED_PHONES.
               Uses the Meta Cloud API (graph.facebook.com) — no SDK
               required, plain HTTP.
  Email        if settings.EMAIL_BACKEND is configured AND the user
               has an email address. Always tries to fall back to
               Django's email backend (which in dev mode prints the
               code to stdout via console.EmailBackend).
  Log          last-resort fallback so the feature still works in
               local-dev when neither WhatsApp nor email are wired.

To activate WhatsApp, set these App Runner env vars:
  WHATSAPP_ACCESS_TOKEN        Meta Graph API token (long-lived/system)
  WHATSAPP_PHONE_NUMBER_ID     numeric ID from Meta Business Manager
  WHATSAPP_TEMPLATE_NAME       name of the pre-approved Authentication
                                template (e.g. "otp_authentication")
  WHATSAPP_TEMPLATE_LANGUAGE   ISO code, default "en"
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
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


def _send_via_whatsapp(phone: str, code: str) -> tuple[bool, str]:
    """Send the OTP via WhatsApp Cloud API (Meta).

    Meta requires a pre-approved "Authentication" template for any
    business-initiated WhatsApp message outside a 24-hour session
    window. The template is created in WhatsApp Business Manager →
    WhatsApp Manager → Message templates → Authentication. The body
    of an Authentication template has exactly one variable, which we
    fill with the 6-digit code.

    Env vars (all required when this channel is used):
      WHATSAPP_ACCESS_TOKEN       — Graph API token
      WHATSAPP_PHONE_NUMBER_ID    — numeric ID of the WABA's phone number
      WHATSAPP_TEMPLATE_NAME      — exact approved-template name
      WHATSAPP_TEMPLATE_LANGUAGE  — ISO language tag, default "en"

    Wire format:
      POST https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages
      Authorization: Bearer {ACCESS_TOKEN}
      Content-Type: application/json
      {
        "messaging_product": "whatsapp",
        "to": "+12019376526",
        "type": "template",
        "template": {
          "name": "<template_name>",
          "language": {"code": "en"},
          "components": [
            {"type": "body",
             "parameters": [{"type": "text", "text": "<code>"}]}
          ]
        }
      }
    """
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    template = getattr(settings, "WHATSAPP_TEMPLATE_NAME", "")
    lang = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en") or "en"
    if not (token and phone_id and template):
        return False, ""

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": code}],
                }
            ],
        },
    }
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            if resp.status >= 400:
                log.warning("whatsapp send returned %s: %r", resp.status, body[:300])
                return False, ""
    except urllib.error.HTTPError as exc:
        # Meta usually returns a JSON error body with code / details.
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            err_body = "<unreadable>"
        log.warning("whatsapp HTTPError %s: %s", exc.code, err_body)
        return False, ""
    except Exception as exc:  # noqa: BLE001
        log.exception("whatsapp send failed: %s", exc)
        return False, ""

    # Mask: +1•••6526 — show country code + last 4 for the destination
    hint = (phone[:2] + "•" * max(len(phone) - 6, 1) + phone[-4:]) if len(phone) >= 6 else phone
    return True, hint


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
        ok, h = _send_via_whatsapp(phone_str, code)
        if ok:
            channel, hint = "whatsapp", h

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
