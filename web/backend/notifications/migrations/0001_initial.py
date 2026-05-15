"""Initial migration — notification_preferences + notification_logs.

`NotificationPreference` is 1:1 with auth user; `NotificationLog` is
write-mostly (one row per send attempt) with indexes on `sent_at` and
`(category, sent_at)` so the per-category recency query in the admin
remains fast as the log grows.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationPreference",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("daily_digest", models.BooleanField(default=False)),
                ("weekly_report", models.BooleanField(default=False)),
                ("breach_alert", models.BooleanField(default=False)),
                ("price_anomaly", models.BooleanField(default=False)),
                ("cost_alarm", models.BooleanField(default=False)),
                ("marketing", models.BooleanField(default=False)),
                ("cc_email", models.EmailField(blank=True, max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_preferences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "notification_preferences"},
        ),
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, serialize=False,
                        default=uuid.uuid4, editable=False,
                    ),
                ),
                ("to_email", models.EmailField(max_length=254)),
                ("from_email", models.EmailField(max_length=254)),
                ("category", models.CharField(max_length=32)),
                ("subject", models.CharField(max_length=256)),
                ("status", models.CharField(max_length=32)),
                (
                    "ses_message_id",
                    models.CharField(max_length=128, blank=True, db_index=True),
                ),
                ("error", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        null=True, blank=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notification_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "notification_logs",
                "indexes": [
                    models.Index(
                        fields=["sent_at"],
                        name="notif_log_sent_idx",
                    ),
                    models.Index(
                        fields=["category", "sent_at"],
                        name="notif_log_cat_sent_idx",
                    ),
                ],
            },
        ),
    ]
