"""REST serializers for the accounts app.

dj-rest-auth wires these into:
  POST /api/auth/registration/   ← RegisterSerializer
  GET  /api/auth/user/           ← UserSerializer
  PATCH /api/auth/user/          ← UserSerializer
"""
from __future__ import annotations

from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import UserDetailsSerializer
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers


class CarPapiRegisterSerializer(RegisterSerializer):
    """Email + password registration with optional phone + name.

    Inherits username from RegisterSerializer (won't actually be saved
    since our User model has no username; allauth's adapter ignores it).
    """

    username = None  # turn off the username field entirely
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    phone = PhoneNumberField(required=False, allow_null=True)
    marketing_opt_in = serializers.BooleanField(required=False, default=False)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data["full_name"] = self.validated_data.get("full_name", "")
        data["phone"] = self.validated_data.get("phone", None)
        data["marketing_opt_in"] = self.validated_data.get("marketing_opt_in", False)
        return data


class CarPapiUserSerializer(UserDetailsSerializer):
    """Adds our custom fields to the /api/auth/user/ payload."""

    phone = PhoneNumberField(allow_null=True, required=False)

    class Meta(UserDetailsSerializer.Meta):
        fields = (
            "pk",
            "email",
            "full_name",
            "phone",
            "is_email_verified",
            "is_phone_verified",
            "marketing_opt_in",
            "date_joined",
        )
        read_only_fields = (
            "pk",
            "email",
            "is_email_verified",
            "is_phone_verified",
            "date_joined",
        )
