"""Step-up admin login: email/password → OTP challenge → JWT.

Flow:

  POST /api/auth/login-step-up/   (this module, `login_step_up`)
    body:  { email, password }
    behavior:
      - validates email+password
      - if user is_staff → creates an AdminOTPChallenge, sends the
        code via the best available channel, returns 200 with
        { challenge: "admin_otp", challenge_token, channel, hint, expires_at }
      - if user is NOT is_staff → returns the normal dj-rest-auth
        response with JWT tokens (forwards to the standard login flow)

  POST /api/admin-otp/verify/
    body:  { challenge_token, code }
    behavior:
      - validates the challenge + code
      - on success: issues JWT access + refresh + user payload, marks
        the challenge as used. Same response shape as
        /api/auth/login/ so the SPA can swap calls cleanly.
      - on failure: 400 with error reason

This is intentionally a separate endpoint from `/api/auth/login/` so
the existing JWT issuance path stays untouched and existing
integrations (mobile, future API clients) keep working without a
required OTP step.
"""
from __future__ import annotations

import logging

from dj_rest_auth.serializers import LoginSerializer
from dj_rest_auth.views import LoginView as DJRALoginView
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .otp import create_and_send_challenge, verify_challenge
from .serializers import CarPapiUserSerializer

log = logging.getLogger("accounts.admin_otp")
User = get_user_model()


def _jwt_response_for(user):
    """Build the same `{access, refresh, user}` payload dj-rest-auth
    returns on a successful /api/auth/login/."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": CarPapiUserSerializer(user).data,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def login_step_up(request):
    """Drop-in replacement for /api/auth/login/ that adds an OTP step
    for staff users.

    Non-staff users get the same JWT response as the regular login.
    Staff users get a 200 with `{challenge: "admin_otp", ...}` and
    must POST /api/admin-otp/verify/ with the code to get JWTs.
    """
    # Reuse dj-rest-auth's serializer so email + password validation
    # (including the locked-out / disabled checks) stays identical.
    ser = LoginSerializer(data=request.data, context={"request": request})
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    user = ser.validated_data["user"]

    if not getattr(user, "is_staff", False):
        # Non-staff: same response shape as /api/auth/login/.
        return Response(_jwt_response_for(user))

    # Staff: short-circuit JWT issuance — emit a challenge instead.
    challenge_token, expires_at, channel, hint = create_and_send_challenge(
        user, request=request,
    )
    log.info(
        "admin step-up issued for user_id=%s channel=%s expires_at=%s",
        user.id, channel, expires_at.isoformat(),
    )
    return Response(
        {
            "challenge": "admin_otp",
            "challenge_token": challenge_token,
            "channel": channel,
            "destination_hint": hint,
            "expires_at": expires_at.isoformat(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp(request):
    """Trade a valid challenge+code for a JWT.

    Returns the same {access, refresh, user} shape as /api/auth/login/.
    """
    token = (request.data.get("challenge_token") or "").strip()
    code = (request.data.get("code") or "").strip()
    if not token or not code:
        return Response(
            {"detail": "challenge_token and code are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user, err = verify_challenge(token, code)
    if err:
        return Response(
            {"detail": err},
            status=status.HTTP_400_BAD_REQUEST,
        )
    log.info("admin step-up verified for user_id=%s", user.id)
    return Response(_jwt_response_for(user))


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_otp(request):
    """Generate a fresh challenge for the same user the original
    challenge was issued to. The SPA can call this if the user didn't
    receive the code.
    """
    token = (request.data.get("challenge_token") or "").strip()
    if not token:
        return Response(
            {"detail": "challenge_token is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    from .models import AdminOTPChallenge
    try:
        prev = AdminOTPChallenge.objects.select_related("user").get(
            challenge_token=token,
        )
    except AdminOTPChallenge.DoesNotExist:
        return Response({"detail": "unknown_challenge"}, status=400)

    new_token, expires_at, channel, hint = create_and_send_challenge(
        prev.user, request=request,
    )
    return Response(
        {
            "challenge": "admin_otp",
            "challenge_token": new_token,
            "channel": channel,
            "destination_hint": hint,
            "expires_at": expires_at.isoformat(),
        }
    )
