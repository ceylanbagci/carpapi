# Skill — Send email notification

> How CarPapi agents emit email notifications (digests, alerts, weekly
> reports). One in-process entry point, SES under the hood, per-user
> preference gating, audit-logged.

## Preflight

- **RDS-first**: `source data/secrets/rds.env` before any agent/script
  that touches the DB (see `skills/rds-first-skill.md`).
- **App Runner-first for SES**: when running locally, you'll hit SES
  with the AWS profile (`AWS_PROFILE=carpapi` or implicit). When running
  inside App Runner, the `CarPapiAppRunnerInstanceRole` already carries
  the `CarPapiSESSend` inline policy — no creds wrangling needed.
- **Sandbox awareness**: `aws sesv2 get-account --region us-east-1` and
  check `ProductionAccessEnabled`. While in sandbox, sends to
  unverified addresses come back with `STATUS_SKIPPED_SANDBOX`. The
  six addresses verified so far: `info@`, `do-not-reply@`, `admin@`,
  `marketing@`, `agent@`, `ceylanibagci@gmail.com`.

## Entry point

```python
from notifications.email import send_email
from notifications.models import (
    CATEGORY_DAILY_DIGEST,
    CATEGORY_BREACH_ALERT,
    CATEGORY_WEEKLY_REPORT,
    CATEGORY_PRICE_ANOMALY,
    CATEGORY_COST_ALARM,
    CATEGORY_MARKETING,
    CATEGORY_TRANSACTIONAL,
)

result = send_email(
    to="admin@carpappi.com",
    subject="[CarPapi] daily digest 2026-05-15",
    body_html="<h2>Yesterday</h2><p>...</p>",
    category=CATEGORY_DAILY_DIGEST,
    user=user_obj,        # so the preference check + audit linkage fire
)
if not result.ok:
    log.warning("notify failed: %s", result.log_row.error)
```

That's the whole API. `send_email` never raises — inspect
`result.ok` (which checks `result.log_row.status == "sent"`).

## Category → From rules

| Category               | Default `From`            |
|------------------------|---------------------------|
| `transactional`        | `do-not-reply@carpappi.com` |
| `daily_digest`         | `agent@carpappi.com`      |
| `weekly_report`        | `agent@carpappi.com`      |
| `breach_alert`         | `agent@carpappi.com`      |
| `price_anomaly`        | `agent@carpappi.com`      |
| `cost_alarm`           | `agent@carpappi.com`      |
| `marketing`            | `marketing@carpappi.com`  |

Override with `from_address=` if you need to (e.g. customer-service
replies from `info@`). The address must be a verified SES identity
under `carpappi.com` or the role policy will reject it.

## Preference gating

- **Transactional** always sends (password resets, email confirmation
  links, account-deletion notices). Skipping these would break the
  account.
- **Everything else** checks `NotificationPreference.allows(category)`.
  If `False`, `send_email` writes a `STATUS_SKIPPED_PREFERENCE` log
  row and returns — no SES call, no spend.

Users manage their preferences via the SPA Settings page
(`/settings`) which talks to `GET/PATCH /api/notifications/preferences/`.

## Recipient sources

Agents that run unattended (cron-style) don't have a `user` context.
Two patterns:

1. **Fan-out to subscribers**: select users with the category enabled,
   loop:
   ```python
   from django.contrib.auth import get_user_model
   from notifications.models import NotificationPreference
   User = get_user_model()
   subs = User.objects.filter(
       notification_preferences__daily_digest=True,
       is_active=True,
   )
   for u in subs:
       send_email(to=u.email, ..., user=u, category=CATEGORY_DAILY_DIGEST)
   ```

2. **Operational alert**: ship to a fixed role address.
   ```python
   send_email(
       to="admin@carpappi.com",
       subject="[CarPapi] scrape-watchdog breach",
       body_html="...",
       category=CATEGORY_BREACH_ALERT,
       # no `user` arg — bypasses preference check
   )
   ```

Pattern 1 respects user prefs; pattern 2 always sends (intentional
for on-call traffic).

## Composing the body

- Always supply HTML. Plain-text fallback is auto-derived from a cheap
  tag-strip — fine for most agent digests, but supply your own
  `body_text=` when the formatting matters (tables, lists).
- Keep subjects under 80 chars; SES adds the `mail.carpappi.com` reply
  path automatically.
- Use the `[CarPapi]` prefix in subjects for the SPA / mobile inbox to
  filter on. Add the verb second: `[CarPapi] breach: scrape-monitor null-rate 0.34`.

## Audit trail

Every send (or skipped send) writes one `NotificationLog` row:

```sql
SELECT category, status, COUNT(*)
FROM notification_logs
WHERE sent_at > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2 ORDER BY 1;
```

Useful for the `data-quality-auditor` weekly report.

## What this skill does NOT cover

- **Receiving mail** (someone emails `info@`) — separate inbound-SES
  layer with MX + S3 rules. Not deployed yet.
- **In-app notifications** (bell icon in the SPA) — would be a
  `NotificationInApp` model + WebSocket push. Future.
- **SMS / WhatsApp** — would reuse the WhatsApp Cloud API plumbing in
  `accounts/otp.py`. Not part of this skill.

## Failure modes

| Symptom                                          | Likely cause                                           | Fix                                                                  |
|--------------------------------------------------|--------------------------------------------------------|----------------------------------------------------------------------|
| `status=skipped_sandbox`                         | SES still in sandbox, recipient not verified           | Verify the address, or have the user request prod access in console  |
| `status=skipped_preference`                      | User opted out of that category                        | Working as designed                                                  |
| `status=failed code=MessageRejected`             | Sending identity not verified or DKIM not yet live     | Wait for DNS propagation; re-check `aws ses get-identity-verification-attributes` |
| `status=failed code=Throttling`                  | Hit `MaxSendRate` (1/s in sandbox, ~14/s in prod)      | Add a sleep between sends in fan-out loops                           |
| `status=failed code=AccessDenied`                | App Runner role missing `ses:SendEmail` on the identity | Re-attach `CarPapiSESSend` inline policy                             |
