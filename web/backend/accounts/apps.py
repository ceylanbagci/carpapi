from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """User accounts + auth.

    Custom User model uses email as the unique identifier (no username),
    adds full_name + phone for real-world signup flows, and supports
    Google OAuth via django-allauth.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts"
