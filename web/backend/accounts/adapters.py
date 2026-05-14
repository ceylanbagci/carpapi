"""Custom allauth adapters.

Two reasons we need these instead of allauth's defaults:

1. **Email-as-username**: our User model has no `username` field at
   all. allauth's default `DefaultAccountAdapter.populate_username`
   tries to set `user.username = generate_unique_username(...)`,
   which crashes. Override `populate_username` to no-op.

2. **Google → User field mapping**: when a user signs in via Google,
   allauth's `DefaultSocialAccountAdapter.populate_user` writes
   `first_name`/`last_name` (which we don't expose). Map to our
   `full_name` instead, and mark `is_email_verified=True` because
   Google's `email_verified` claim already gates them.
"""
from __future__ import annotations

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    """Local email/password account adapter."""

    def populate_username(self, request, user):
        # User model has no `username` field; do nothing.
        return user

    def save_user(self, request, user, form, commit=True):
        """Capture marketing_opt_in from the signup form, if present."""
        user = super().save_user(request, user, form, commit=False)
        data = form.cleaned_data if hasattr(form, "cleaned_data") else {}
        if "full_name" in data:
            user.full_name = data["full_name"]
        if "phone" in data:
            user.phone = data["phone"]
        user.marketing_opt_in = bool(data.get("marketing_opt_in"))
        if commit:
            user.save()
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google / Facebook / etc. account adapter."""

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        # Google gives us `name` (full), `given_name`, `family_name`.
        # Prefer `name`, fall back to "given family", fall back to email.
        full_name = (
            data.get("name")
            or " ".join(p for p in (data.get("first_name"), data.get("last_name")) if p)
            or ""
        )
        if full_name:
            user.full_name = full_name
        # Providers we trust set this. Anyone who lands here via Google
        # is already email-verified by Google.
        provider = sociallogin.account.provider if sociallogin and sociallogin.account else None
        if provider in {"google", "apple"} and data.get("email"):
            user.is_email_verified = True
        return user
