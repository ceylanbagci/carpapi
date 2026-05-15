"""SES email handler.

`send_email(...)` is the only public entry point. It:

  1. Resolves the recipient user (if any) and checks their
     `NotificationPreference` against `category`. Transactional emails
     bypass the check.
  2. Calls `boto3.client('ses').send_email()` with both an HTML and a
     plaintext body. The plaintext body is auto-derived from HTML when
     not supplied — important for spam scoring.
  3. Records the outcome to `NotificationLog`. The SES MessageId is
     captured so SNS feedback events can be correlated.
  4. Returns the log row. Never raises on send failures — callers can
     check `.status == 'sent'`.

Configuration (via env vars on App Runner):

  - AWS region: implicit from the App Runner instance role.
  - `CARPAPI_NOTIFICATIONS_DEFAULT_FROM` (default
    `do-not-reply@carpappi.com`).
  - `CARPAPI_NOTIFICATIONS_MARKETING_FROM` (default
    `marketing@carpappi.com`).
  - `CARPAPI_NOTIFICATIONS_AGENT_FROM` (default
    `agent@carpappi.com`).
  - `CARPAPI_NOTIFICATIONS_SES_REGION` (default `us-east-1`).
  - `CARPAPI_NOTIFICATIONS_DRYRUN` set to `1` to write a log row but
    NOT call SES (useful for local dev without SES sandbox access).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .models import (
    CATEGORY_MARKETING,
    CATEGORY_TRANSACTIONAL,
    NotificationLog,
    NotificationPreference,
)

log = logging.getLogger("carpapi.notifications.email")


SES_REGION = os.environ.get("CARPAPI_NOTIFICATIONS_SES_REGION", "us-east-1")
DEFAULT_FROM = os.environ.get(
    "CARPAPI_NOTIFICATIONS_DEFAULT_FROM", "do-not-reply@carpappi.com"
)
MARKETING_FROM = os.environ.get(
    "CARPAPI_NOTIFICATIONS_MARKETING_FROM", "marketing@carpappi.com"
)
AGENT_FROM = os.environ.get(
    "CARPAPI_NOTIFICATIONS_AGENT_FROM", "agent@carpappi.com"
)
DRYRUN = os.environ.get("CARPAPI_NOTIFICATIONS_DRYRUN", "").lower() in ("1", "true")


@dataclass
class SendResult:
    """Returned by send_email — caller can check `.ok`."""
    log_row: NotificationLog

    @property
    def ok(self) -> bool:
        return self.log_row.status == NotificationLog.STATUS_SENT


def _strip_html(html: str) -> str:
    """Cheap HTML → plaintext fallback. Replaces <br> + paragraphs with
    newlines and strips remaining tags. Not bulletproof — callers should
    supply their own `body_text` for anything important."""
    out = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    out = re.sub(r"</p>", "\n\n", out, flags=re.IGNORECASE)
    out = re.sub(r"<[^>]+>", "", out)
    return out.strip()


def _from_for_category(category: str, override: Optional[str]) -> str:
    if override:
        return override
    if category == CATEGORY_MARKETING:
        return MARKETING_FROM
    if category.startswith("agent_") or category in (
        "daily_digest", "weekly_report", "breach_alert",
        "price_anomaly", "cost_alarm",
    ):
        return AGENT_FROM
    return DEFAULT_FROM


def send_email(
    *,
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    from_address: Optional[str] = None,
    category: str = CATEGORY_TRANSACTIONAL,
    user=None,
    reply_to: Optional[str] = None,
) -> SendResult:
    """Send one email. Always returns a SendResult; never raises.

    `to` — destination email address.
    `subject`, `body_html` — message content.
    `body_text` — plaintext fallback (auto-derived from HTML if absent).
    `from_address` — override the category-derived From. Must be a
        verified SES identity under carpappi.com.
    `category` — one of `notifications.models.CATEGORY_*`. Transactional
        bypasses user preferences.
    `user` — the recipient User model instance, if known. Allows
        preference-based suppression + per-user audit linkage.
    `reply_to` — Reply-To header. Default = `info@carpappi.com` for
        marketing, none for transactional (replies discouraged).
    """
    if body_text is None:
        body_text = _strip_html(body_html)

    from_email = _from_for_category(category, from_address)

    # Preference check — transactional always passes.
    if user is not None and category != CATEGORY_TRANSACTIONAL:
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        if not prefs.allows(category):
            row = NotificationLog.objects.create(
                user=user,
                to_email=to,
                from_email=from_email,
                category=category,
                subject=subject[:256],
                status=NotificationLog.STATUS_SKIPPED_PREFERENCE,
            )
            log.info(
                "notify SKIP (preference) user=%s cat=%s to=%s",
                getattr(user, "id", "?"), category, to,
            )
            return SendResult(log_row=row)

    if DRYRUN:
        row = NotificationLog.objects.create(
            user=user,
            to_email=to,
            from_email=from_email,
            category=category,
            subject=subject[:256],
            status=NotificationLog.STATUS_SENT,
            ses_message_id="dryrun-stub",
        )
        log.info("notify DRYRUN cat=%s to=%s subj=%r", category, to, subject)
        return SendResult(log_row=row)

    client = boto3.client("ses", region_name=SES_REGION)
    destination = {"ToAddresses": [to]}
    message = {
        "Subject": {"Data": subject, "Charset": "UTF-8"},
        "Body": {
            "Html": {"Data": body_html, "Charset": "UTF-8"},
            "Text": {"Data": body_text, "Charset": "UTF-8"},
        },
    }
    kwargs = {
        "Source": from_email,
        "Destination": destination,
        "Message": message,
    }
    if reply_to:
        kwargs["ReplyToAddresses"] = [reply_to]
    elif category == CATEGORY_MARKETING:
        kwargs["ReplyToAddresses"] = ["info@carpappi.com"]

    try:
        resp = client.send_email(**kwargs)
        msg_id = resp.get("MessageId", "")
        row = NotificationLog.objects.create(
            user=user,
            to_email=to,
            from_email=from_email,
            category=category,
            subject=subject[:256],
            status=NotificationLog.STATUS_SENT,
            ses_message_id=msg_id,
        )
        log.info(
            "notify SENT cat=%s to=%s msg_id=%s subj=%r",
            category, to, msg_id, subject,
        )
        return SendResult(log_row=row)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        # SES sandbox: "MessageRejected" when sending to a non-verified
        # address. Log distinctly so the SPA can surface "this address
        # isn't verified" instead of a generic failure.
        status = (
            NotificationLog.STATUS_SKIPPED_SANDBOX
            if code == "MessageRejected" and "not verified" in str(exc).lower()
            else NotificationLog.STATUS_FAILED
        )
        row = NotificationLog.objects.create(
            user=user,
            to_email=to,
            from_email=from_email,
            category=category,
            subject=subject[:256],
            status=status,
            error=f"{code}: {exc}",
        )
        log.warning(
            "notify FAIL cat=%s to=%s code=%s err=%s",
            category, to, code, exc,
        )
        return SendResult(log_row=row)
