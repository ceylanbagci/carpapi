"""WhatsApp Cloud API webhook endpoint (Meta).

We use WhatsApp ONLY to send OTP codes — we don't process inbound
WhatsApp messages or react to delivery status. So this endpoint is
minimal:

  GET  → verification handshake. Meta calls
         /api/whatsapp/webhook/?hub.mode=subscribe
                                &hub.verify_token=<shared>
                                &hub.challenge=<random>
         We echo `hub.challenge` back when the shared `verify_token`
         matches `settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN`.

  POST → event delivery. We log the payload (so it's searchable in
         CloudWatch / Django logs for audit) and return 200 so Meta
         doesn't retry. We deliberately do NOT validate the payload
         signature here because Meta's signing is optional for
         single-app accounts and adding HMAC validation is a separate
         hardening pass.

The verify_token is a shared secret the user picks when configuring
the webhook in Meta's App Dashboard. Generate one with:

    python3 -c "import secrets; print(secrets.token_urlsafe(32))"

…and set it as the App Runner env var WHATSAPP_WEBHOOK_VERIFY_TOKEN.
Paste the same value into Meta's "Verify token" field when wiring
the webhook URL.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

log = logging.getLogger("accounts.whatsapp.webhook")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        verify_token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        expected = getattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
        if mode == "subscribe" and expected and verify_token == expected:
            log.info("whatsapp webhook verification OK")
            return HttpResponse(challenge, content_type="text/plain")
        log.warning(
            "whatsapp webhook verification mismatch: mode=%r match_token=%s",
            mode,
            bool(expected and verify_token == expected),
        )
        return HttpResponseForbidden("verify token mismatch")

    # POST — Meta delivered an event.
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {"_raw": request.body[:300].decode("utf-8", errors="replace")}

    # Pull out the most useful identifiers without scanning the whole
    # tree for grep-friendly log lines. The full payload still gets
    # the json.dumps below for debugging.
    obj = payload.get("object")
    entry_count = len(payload.get("entry") or [])
    log.info(
        "whatsapp webhook event object=%s entries=%d payload=%s",
        obj,
        entry_count,
        json.dumps(payload)[:1500],
    )
    return HttpResponse(status=200)
