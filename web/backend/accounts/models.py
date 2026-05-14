"""Custom User model for CarPapi.

Design choices:
  - Email is the unique identifier (USERNAME_FIELD = "email").
  - `username` is removed entirely — fewer fields to worry about,
    no ambiguity between email-vs-username at login.
  - `full_name` stores the display name (no separate first/last —
    keeps signup forms simple and works for any culture).
  - `phone` is optional at signup but required before checkout-style
    actions (enforced at the view layer, not the model).
  - `is_phone_verified` / `is_email_verified` flags are tracked
    independently because Google-OAuth signups skip the email
    verification email but pre-verify their email via the
    provider's `email_verified` claim.
"""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField


class UserManager(BaseUserManager):
    """Email-as-username manager.

    BaseUserManager's default `create_user` / `create_superuser`
    require a `username` argument — we override to use `email` and
    drop the `username` field entirely.
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)  # hashes; supports unusable for OAuth-only
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        extra.setdefault("is_email_verified", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Email-as-username user with phone + display name."""

    # Drop username entirely — see USERNAME_FIELD below.
    username = None

    email = models.EmailField(
        _("email address"),
        unique=True,
        help_text=_("Primary identifier; used to log in."),
    )
    full_name = models.CharField(
        _("full name"),
        max_length=200,
        blank=True,
        help_text=_("How the user wants to be addressed."),
    )
    phone = PhoneNumberField(
        _("phone number"),
        blank=True,
        null=True,
        unique=True,
        help_text=_("E.164 format (e.g. +14155551234). Optional at signup; required before phone-gated actions."),
    )
    is_email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Set by the email-confirmation flow (allauth) or by an OAuth provider's verified-email claim."),
    )
    is_phone_verified = models.BooleanField(
        _("phone verified"),
        default=False,
        help_text=_("Set when the user completes phone OTP verification."),
    )
    marketing_opt_in = models.BooleanField(
        _("marketing emails"),
        default=False,
        help_text=_("Did the user opt in to product + dealer-promo emails at signup?"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []  # createsuperuser only asks for email + password

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.full_name or self.email

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else self.email


class AdminOTPChallenge(models.Model):
    """One-time-code challenge for admin (is_staff) login step-up.

    Lifecycle:
      1. User POSTs /api/auth/login/ with email+password. Backend
         validates the password. If the user is_staff, instead of
         issuing a JWT, it creates an AdminOTPChallenge row, sends
         a 6-digit `code` to the user's verified contact channel
         (email today, SMS tomorrow), and returns the challenge
         id (`challenge_token`) + expiry to the client.
      2. SPA shows the OTP form; user enters the code.
      3. SPA POSTs /api/admin-otp/verify/ with the challenge_token +
         code. If still valid + unused + matches: mark `used_at`,
         issue the JWT, and return it.
      4. Any expired / mismatched / exhausted-attempts row is rejected.

    Codes are 6-digit numeric, valid for 10 minutes, and capped at
    5 wrong attempts before invalidation. We store the hash, not the
    plaintext, so a DB read won't leak codes.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="admin_otp_challenges",
    )
    # Random URL-safe identifier the client echoes back to /verify/.
    challenge_token = models.CharField(max_length=64, unique=True, db_index=True)
    # SHA-256 of the 6-digit code. We never store the plaintext.
    code_hash = models.CharField(max_length=64)
    # Which channel the code was delivered through. Useful for the UI
    # ("we sent a code to +1•••6526" vs "we emailed you a code").
    channel = models.CharField(
        max_length=16,
        choices=[
            ("email", "Email"),
            ("sms", "SMS"),
            ("log", "Log (dev only)"),
        ],
        default="email",
    )
    destination_hint = models.CharField(
        max_length=200,
        blank=True,
        help_text="Masked destination shown to the user, e.g. j••@gmail.com or +1•••6526.",
    )
    attempts = models.PositiveIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "created_at")),
        ]

    def __str__(self) -> str:
        return f"AdminOTPChallenge<{self.user_id} {self.challenge_token[:8]} {self.channel}>"

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= 5
