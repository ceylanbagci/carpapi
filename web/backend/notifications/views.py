"""REST endpoints for /api/notifications/.

Two views:

  - `PreferencesView` (GET/PATCH /api/notifications/preferences/) —
    self-service for the authenticated user. The SPA Settings page
    renders a checkbox per category and PATCHes back.

  - `SendTestView` (POST /api/notifications/test/) — auth required,
    fires a single test email to the caller's address so the user can
    confirm SES is wired without waiting for the next daily digest.

Agents do NOT hit these endpoints — they import
`notifications.email.send_email()` directly (in-process). The HTTP
surface is purely for the SPA.
"""

from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .email import send_email
from .models import (
    ALL_USER_CATEGORIES,
    CATEGORY_TRANSACTIONAL,
    NotificationPreference,
)


# UI labels — the SPA renders these next to each checkbox.
CATEGORY_LABELS = {
    "daily_digest":    "Daily digest (yesterday's spend, scrape summary)",
    "weekly_report":   "Weekly data-quality report",
    "breach_alert":    "Scrape watchdog breach alerts",
    "price_anomaly":   "Price-anomaly findings",
    "cost_alarm":      "AWS cost alarms (50/80/100% budget)",
    "marketing":       "New listings + dealer promos",
}


def _serialize(prefs: NotificationPreference) -> dict:
    return {
        "categories": [
            {
                "key": key,
                "label": CATEGORY_LABELS[key],
                "enabled": prefs.allows(key),
            }
            for key in ALL_USER_CATEGORIES
        ],
        "cc_email": prefs.cc_email,
        "updated_at": prefs.updated_at.isoformat(),
    }


class PreferencesView(APIView):
    """GET → current prefs; PATCH → update one or more category toggles
    or `cc_email`."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(
            user=request.user,
        )
        return Response(_serialize(prefs))

    def patch(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(
            user=request.user,
        )
        data = request.data or {}

        # `categories` ships as {"daily_digest": true, "marketing": false, ...}
        cats = data.get("categories") or {}
        if not isinstance(cats, dict):
            return Response(
                {"detail": "categories must be an object"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for key, value in cats.items():
            if key not in ALL_USER_CATEGORIES:
                continue  # silently ignore unknowns (forward-compat)
            setattr(prefs, key, bool(value))

        if "cc_email" in data:
            cc = (data["cc_email"] or "").strip()
            prefs.cc_email = cc

        prefs.save()
        return Response(_serialize(prefs))


class SendTestView(APIView):
    """POST /api/notifications/test/ — fires a test email to request.user.email.

    Useful for verifying SES wiring without scheduling a real agent run.
    Returns the NotificationLog row.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.email:
            return Response(
                {"detail": "user has no email address"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        body_html = (
            "<p>This is a test email from CarPapi notifications.</p>"
            "<p>If you see this, your SES wiring is working.</p>"
            "<p style='color:#666;font-size:12px'>"
            "Sent via the /api/notifications/test/ endpoint."
            "</p>"
        )
        result = send_email(
            to=user.email,
            subject="CarPapi notification test",
            body_html=body_html,
            user=user,
            category=CATEGORY_TRANSACTIONAL,
        )
        row = result.log_row
        return Response({
            "ok": result.ok,
            "status": row.status,
            "ses_message_id": row.ses_message_id,
            "error": row.error,
            "to": row.to_email,
            "from": row.from_email,
        })
