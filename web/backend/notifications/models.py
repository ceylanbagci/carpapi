"""Notification models — per-user email preferences + delivery log.

`NotificationPreference` is keyed 1-to-1 to a user. Each notification
category is a separate boolean so the user can opt out of marketing
without losing transactional emails (password reset, email confirmation,
etc.). Transactional emails ignore the preferences entirely — they're
required for the account to function.

`NotificationLog` is a thin audit trail of every send attempt. We log
the SES MessageId on success so bounces / complaints from the SNS
feedback loop can be linked back to the originating row.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


# Notification categories — kept here so the SPA can render checkboxes
# off a single source of truth (see views.py::CATEGORY_LABELS).
CATEGORY_DAILY_DIGEST = "daily_digest"
CATEGORY_BREACH_ALERT = "breach_alert"
CATEGORY_WEEKLY_REPORT = "weekly_report"
CATEGORY_PRICE_ANOMALY = "price_anomaly"
CATEGORY_COST_ALARM = "cost_alarm"
CATEGORY_MARKETING = "marketing"
CATEGORY_TRANSACTIONAL = "transactional"  # always sent — not user-toggleable

ALL_USER_CATEGORIES = (
    CATEGORY_DAILY_DIGEST,
    CATEGORY_BREACH_ALERT,
    CATEGORY_WEEKLY_REPORT,
    CATEGORY_PRICE_ANOMALY,
    CATEGORY_COST_ALARM,
    CATEGORY_MARKETING,
)


class NotificationPreference(models.Model):
    """One row per user. Defaults: all alerts ON, marketing OFF."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )

    # Operational alerts — agents push their daily/weekly/breach outputs
    # here. Default ON for staff users (they want to know), OFF for
    # regular end-users (they don't care about our scrape pipeline).
    # views.py::default_for_user() decides at create time.
    daily_digest = models.BooleanField(default=False)
    weekly_report = models.BooleanField(default=False)
    breach_alert = models.BooleanField(default=False)
    price_anomaly = models.BooleanField(default=False)
    cost_alarm = models.BooleanField(default=False)

    # End-user marketing emails — opt-in. Tracks `accounts.User.marketing_opt_in`
    # at signup but kept as its own field so the user can later toggle just
    # this without affecting account-level marketing flag.
    marketing = models.BooleanField(default=False)

    # Optional alternate destination — if blank, sends go to `user.email`.
    # Useful when admin@carpappi.com owns the dashboard but wants the
    # alerts mirrored to their personal inbox during on-call.
    cc_email = models.EmailField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_preferences"

    def __str__(self) -> str:  # pragma: no cover
        return f"NotificationPreference<{self.user_id}>"

    def allows(self, category: str) -> bool:
        """Whether `category` should be delivered for this user.
        Transactional always returns True (ignores the toggles)."""
        if category == CATEGORY_TRANSACTIONAL:
            return True
        return bool(getattr(self, category, False))


class NotificationLog(models.Model):
    """Per-send audit row. SES emits an Idempotent MessageId we record."""

    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED_PREFERENCE = "skipped_preference"
    STATUS_SKIPPED_SANDBOX = "skipped_sandbox"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="notification_logs",
    )
    to_email = models.EmailField()
    from_email = models.EmailField()
    category = models.CharField(max_length=32)
    subject = models.CharField(max_length=256)
    status = models.CharField(max_length=32)
    ses_message_id = models.CharField(max_length=128, blank=True, db_index=True)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_logs"
        indexes = [
            models.Index(fields=["sent_at"]),
            models.Index(fields=["category", "sent_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"NotificationLog<{self.id} {self.category} {self.status}>"
