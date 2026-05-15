"""Handler for the `aws-cost-sentinel` agent.

What it does (daily 09:00 UTC, per the EventBridge schedule):

  1. Pull yesterday's AWS spend via Cost Explorer
     (`aws ce get-cost-and-usage`), grouped by service.
  2. Pull MTD totals + project the month-end run-rate.
  3. Compare against the monthly budget ($100/mo default; configurable
     via the `CARPAPI_MONTHLY_BUDGET_USD` env var on the Lambda).
  4. If MTD is past 50% / 80% / 100% of budget, escalate the alert
     `tone` from green → yellow → red.
  5. Build an HTML digest. Send via SES to `admin@carpappi.com` using
     the `notifications.email.send_email()` helper (same module the
     Django app uses — both share the carpapi-agent-base image's copy
     of the notifications package).

The Lambda role needs:
  - `ce:GetCostAndUsage`
  - `ses:SendEmail` on `*@carpappi.com`
  - `bedrock:GetModelInvocationLoggingConfiguration` (read-only, not
    used yet — placeholder for the per-model token-usage line we'll
    add once Bedrock has been live for a week).

No DB access required — purely AWS API + SES.

Return shape:
    {"ok": True, "yesterday_usd": <float>, "mtd_usd": <float>,
     "budget_pct": <float>, "tone": "green"|"yellow"|"red",
     "ses_message_id": <str>}

Failure handling:
  - SES sandbox / non-verified recipient: returns
    `ok=False, error="skipped_sandbox"`. Does NOT raise — the
    sentinel is best-effort and shouldn't take down the Lambda.
  - Cost Explorer permission error: raises so the Lambda retry
    policy kicks in and CloudWatch alarms fire.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger("carpapi.agent.aws_cost_sentinel")


# ── Config ───────────────────────────────────────────────────────────
MONTHLY_BUDGET_USD = float(os.environ.get("CARPAPI_MONTHLY_BUDGET_USD", "100"))
ADMIN_EMAIL = os.environ.get("CARPAPI_ADMIN_EMAIL", "admin@carpappi.com")
PROJECT_TAG = os.environ.get("CARPAPI_PROJECT_TAG", "CarPapi")


# ── Cost Explorer ────────────────────────────────────────────────────

def _yesterday_utc() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)


def _month_to_date_range() -> tuple[dt.date, dt.date]:
    today = dt.datetime.now(dt.timezone.utc).date()
    return today.replace(day=1), today


def _fetch_costs() -> dict:
    """Returns
        {
          "yesterday_total": float,
          "yesterday_by_service": [(service, usd), ...],   # top 5
          "mtd_total": float,
          "month_end_projection": float,
        }
    """
    ce = boto3.client("ce", region_name="us-east-1")
    y = _yesterday_utc()

    # Yesterday's spend by service.
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": y.isoformat(), "End": (y + dt.timedelta(days=1)).isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    groups = resp.get("ResultsByTime", [{}])[0].get("Groups", []) or []
    by_service = sorted(
        ((g["Keys"][0], float(g["Metrics"]["UnblendedCost"]["Amount"])) for g in groups),
        key=lambda kv: -kv[1],
    )
    yesterday_total = sum(v for _, v in by_service)

    # Month-to-date total (no group-by — cheaper).
    mtd_start, mtd_end = _month_to_date_range()
    if mtd_start == mtd_end:
        # 1st of month — no spend yet today. CE rejects same-day range.
        mtd_total = 0.0
    else:
        mtd_resp = ce.get_cost_and_usage(
            TimePeriod={"Start": mtd_start.isoformat(), "End": mtd_end.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        mtd_total = float(
            mtd_resp.get("ResultsByTime", [{}])[0].get("Total", {})
            .get("UnblendedCost", {}).get("Amount", 0.0) or 0.0
        )

    # End-of-month projection: linear extrapolation from days-so-far
    # / days-in-month. Cheap, intentionally naive — Cost Explorer's
    # own forecast endpoint costs extra and gives us a similar number.
    days_so_far = (mtd_end - mtd_start).days or 1
    if mtd_end.month == 12:
        first_of_next = mtd_end.replace(year=mtd_end.year + 1, month=1, day=1)
    else:
        first_of_next = mtd_end.replace(month=mtd_end.month + 1, day=1)
    days_in_month = (first_of_next - mtd_start).days
    projection = mtd_total / days_so_far * days_in_month

    return {
        "yesterday_total": yesterday_total,
        "yesterday_by_service": by_service[:5],
        "mtd_total": mtd_total,
        "month_end_projection": projection,
    }


def _tone(mtd_total: float) -> str:
    pct = (mtd_total / MONTHLY_BUDGET_USD) * 100 if MONTHLY_BUDGET_USD else 0
    if pct >= 100:
        return "red"
    if pct >= 80:
        return "amber"
    if pct >= 50:
        return "yellow"
    return "green"


# ── HTML body ───────────────────────────────────────────────────────

def _fmt_usd(v: float) -> str:
    return f"${v:,.2f}"


def _render_body(facts: dict) -> str:
    pct = (facts["mtd_total"] / MONTHLY_BUDGET_USD * 100) if MONTHLY_BUDGET_USD else 0
    tone = _tone(facts["mtd_total"])
    tone_colors = {"green": "#16a34a", "yellow": "#ca8a04", "amber": "#ea580c", "red": "#dc2626"}
    color = tone_colors[tone]

    rows = "".join(
        f"<tr><td style='padding:6px 12px;border-top:1px solid #eee'>{svc}</td>"
        f"<td style='padding:6px 12px;border-top:1px solid #eee;text-align:right;"
        f"font-variant-numeric:tabular-nums'>{_fmt_usd(usd)}</td></tr>"
        for svc, usd in facts["yesterday_by_service"]
    ) or "<tr><td style='padding:6px 12px;color:#888'>no spend yesterday</td></tr>"

    return (
        f"<div style='font-family:Inter,system-ui,sans-serif;max-width:560px;"
        f"margin:24px auto;padding:0 24px;color:#111;line-height:1.55'>"
        f"<h1 style='font-size:20px;margin:0 0 12px'>CarPapi — AWS cost digest</h1>"
        f"<p style='font-size:14px;color:#555'>"
        f"yesterday {dt.date.today() - dt.timedelta(days=1):%Y-%m-%d}: <strong>{_fmt_usd(facts['yesterday_total'])}</strong></p>"
        f"<p style='padding:10px 14px;border-left:4px solid {color};background:#f8f9fa;"
        f"font-size:14px'>MTD <strong>{_fmt_usd(facts['mtd_total'])}</strong> "
        f"= <strong>{pct:.1f}%</strong> of <strong>{_fmt_usd(MONTHLY_BUDGET_USD)}</strong> budget "
        f"(month-end projection: <strong>{_fmt_usd(facts['month_end_projection'])}</strong>) "
        f"— <span style='color:{color};font-weight:600;text-transform:uppercase'>{tone}</span></p>"
        f"<table style='border-collapse:collapse;font-size:14px;margin-top:12px'>"
        f"<thead><tr><th style='text-align:left;padding:6px 12px;color:#555;font-weight:600'>service</th>"
        f"<th style='text-align:right;padding:6px 12px;color:#555;font-weight:600'>USD</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<hr style='border:none;border-top:1px solid #eee;margin:24px 0'>"
        f"<p style='color:#666;font-size:12px'>Daily digest from <code>aws-cost-sentinel</code> agent. "
        f"To adjust the budget, set <code>CARPAPI_MONTHLY_BUDGET_USD</code> on the Lambda.</p>"
        f"</div>"
    )


# ── Handler ─────────────────────────────────────────────────────────

def handle(event: dict, context: Any) -> dict:
    """Entry point invoked by `agent_runner.lambda_handler`."""
    log.info("aws-cost-sentinel start")

    try:
        facts = _fetch_costs()
    except ClientError as exc:
        log.error("cost-explorer failed: %s", exc)
        raise  # Lambda retry + DLQ

    body_html = _render_body(facts)
    tone = _tone(facts["mtd_total"])
    subject_prefix = "[CarPapi]" if tone == "green" else f"[CarPapi {tone.upper()}]"
    subject = (
        f"{subject_prefix} AWS cost — "
        f"yesterday {_fmt_usd(facts['yesterday_total'])}, "
        f"MTD {_fmt_usd(facts['mtd_total'])}"
    )

    # Use the notifications.email helper if it's importable (it ships
    # in the agent image alongside the Django backend code). Fall back
    # to a direct boto3 SES call if the import fails — keeps the agent
    # decoupled from the Django app's settings module.
    try:
        from notifications.email import send_email  # type: ignore
        from notifications.models import CATEGORY_COST_ALARM  # type: ignore
        result = send_email(
            to=ADMIN_EMAIL,
            subject=subject,
            body_html=body_html,
            category=CATEGORY_COST_ALARM,
        )
        ok = result.ok
        msg_id = result.log_row.ses_message_id
        err = result.log_row.error or ""
    except (ImportError, Exception) as exc:  # noqa: BLE001
        log.info("notifications.email unavailable (%s), falling back to direct SES", exc)
        try:
            ses = boto3.client("ses", region_name="us-east-1")
            resp = ses.send_email(
                Source="agent@carpappi.com",
                Destination={"ToAddresses": [ADMIN_EMAIL]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": body_html, "Charset": "UTF-8"},
                        "Text": {"Data": (
                            f"CarPapi AWS cost digest\n"
                            f"yesterday: {_fmt_usd(facts['yesterday_total'])}\n"
                            f"MTD: {_fmt_usd(facts['mtd_total'])} "
                            f"({facts['mtd_total']/MONTHLY_BUDGET_USD*100:.1f}% of "
                            f"{_fmt_usd(MONTHLY_BUDGET_USD)} budget)\n"
                            f"month-end projection: {_fmt_usd(facts['month_end_projection'])}\n"
                            f"tone: {tone}\n"
                        ), "Charset": "UTF-8"},
                    },
                },
            )
            ok = True
            msg_id = resp.get("MessageId", "")
            err = ""
        except ClientError as ses_exc:
            code = ses_exc.response.get("Error", {}).get("Code", "Unknown")
            if code == "MessageRejected":
                log.warning("SES sandbox blocked send: %s", ses_exc)
                return {
                    "ok": False, "error": "skipped_sandbox",
                    "tone": tone, "yesterday_usd": facts["yesterday_total"],
                    "mtd_usd": facts["mtd_total"],
                }
            log.error("SES send failed: %s", ses_exc)
            raise

    return {
        "ok": ok,
        "ses_message_id": msg_id,
        "error": err,
        "tone": tone,
        "yesterday_usd": facts["yesterday_total"],
        "mtd_usd": facts["mtd_total"],
        "budget_pct": (facts["mtd_total"] / MONTHLY_BUDGET_USD * 100) if MONTHLY_BUDGET_USD else 0,
        "month_end_projection_usd": facts["month_end_projection"],
    }
