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
