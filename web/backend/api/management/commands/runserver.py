"""Override Django's runserver so the dev server boots even when the
configured Postgres host isn't reachable yet. The migration check still
runs, but a connection failure is logged as a warning instead of
crashing startup — this is dev-only and keeps the React UI usable
(it shows an 'API unavailable' banner) while the operator points
``CARPAPI_DB_HOST`` at the right box.
"""
from __future__ import annotations

from django.contrib.staticfiles.management.commands.runserver import (
    Command as RunserverCommand,
)
from django.db.utils import OperationalError


class Command(RunserverCommand):
    def check_migrations(self):
        try:
            super().check_migrations()
        except OperationalError as exc:
            self.stdout.write(self.style.WARNING(
                f"\n[runserver] DB unreachable, skipping migration check: {exc}\n"
                "  Set CARPAPI_DB_HOST/PORT to point at your Postgres "
                "and restart for live data.\n"
            ))
