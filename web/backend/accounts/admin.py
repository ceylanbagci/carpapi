"""Django admin registration for the custom User model.

We keep Django's familiar auth admin shape but swap `username`-based
lookups for `email`, and expose verification status + phone for
support flows.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "email",
        "full_name",
        "phone",
        "is_active",
        "is_staff",
        "is_email_verified",
        "is_phone_verified",
        "created_at",
    )
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "is_email_verified",
        "is_phone_verified",
        "marketing_opt_in",
    )
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")

    # Re-shape fieldsets because we removed `username`.
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("full_name", "phone")}),
        (
            _("Verification"),
            {"fields": ("is_email_verified", "is_phone_verified", "marketing_opt_in")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("created_at", "updated_at", "last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "phone", "password1", "password2"),
            },
        ),
    )
