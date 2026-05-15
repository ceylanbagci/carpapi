"""carpapi.notifications — email + (future) in-app notification plumbing.

Two public surfaces:

  1. `notifications.email.send_email(to, subject, body_html, body_text=None,
     from_address='do-not-reply@carpappi.com', category='transactional')` —
     thin wrapper around boto3 SES. Honors per-user `NotificationPreference`
     when `category != 'transactional'`. Logs every attempt to
     `notifications.NotificationLog`.

  2. REST endpoints under `/api/notifications/preferences/` for the SPA
     Settings page to GET/PATCH the current user's prefs.

Operational policy:
  - All marketing/digest emails go from `marketing@carpappi.com`.
  - All system/alert emails go from `do-not-reply@carpappi.com`.
  - The `agent@carpappi.com` identity is reserved for sub-agent-originated
    digests (price-anomaly, scrape-watchdog, data-quality-auditor, cost
    sentinel). The `email-notifier` agent uses this identity.
  - `info@` and `admin@` are reserved for *receiving* (configured in a
    later receiving-infra pass — not part of this commit).
"""

default_app_config = "notifications.apps.NotificationsConfig"
