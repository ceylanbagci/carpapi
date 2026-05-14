"""Idempotent superuser bootstrap.

Reads DJANGO_SUPERUSER_EMAIL + DJANGO_SUPERUSER_PASSWORD from env and
creates the user if it doesn't exist. If the email exists but is not
a superuser, promote it. Safe to run on every container boot.

Used by the Dockerfile's CMD chain so a fresh App Runner deploy
always has at least one admin login available without anyone needing
to shell into a container.

Skipping behaviour:
  - Both env vars empty → no-op + log (lets you boot a service
    without a hardcoded admin if you want; you can `createsuperuser`
    by hand later).
  - Email present but password empty → still creates if missing,
    with a random unusable password (you'd reset via /admin/
    password-reset later).
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently create or promote a superuser from env vars."

    def handle(self, *args, **opts):
        email = (os.environ.get("DJANGO_SUPERUSER_EMAIL") or "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or ""
        full_name = (os.environ.get("DJANGO_SUPERUSER_FULL_NAME") or "").strip()

        if not email:
            self.stdout.write(
                "[ensure_superuser] DJANGO_SUPERUSER_EMAIL not set; skipping."
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": full_name,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "is_email_verified": True,
            },
        )
        if created:
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()
            self.stdout.write(
                f"[ensure_superuser] created superuser {email} "
                f"(password {'set' if password else 'unusable; reset via /admin/'})."
            )
            return

        changed = False
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if password:
            # Re-set password every boot only when explicitly provided;
            # otherwise leave whatever the user changed it to.
            user.set_password(password)
            changed = True
        if changed:
            user.save()
            self.stdout.write(
                f"[ensure_superuser] promoted/refreshed existing user {email}."
            )
        else:
            self.stdout.write(
                f"[ensure_superuser] {email} already a superuser; nothing to do."
            )
