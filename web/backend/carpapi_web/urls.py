from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def root(_request):
    return JsonResponse(
        {
            "service": "carpapi-web",
            "endpoints": [
                "/api/stats/",
                "/api/dealers/",
                "/api/listings/",
                "/api/cars/",
                "/api/makes/",
                "/api/models/",
                "/api/chat/",
                "/api/auth/login/",
                "/api/auth/logout/",
                "/api/auth/registration/",
                "/api/auth/user/",
                "/api/auth/password/reset/",
                "/admin/",
                "/accounts/google/login/",
            ],
        }
    )


from accounts.views_admin_otp import login_step_up, resend_otp, verify_otp

urlpatterns = [
    path("", root),
    # Django admin — staff-only management UI.
    path("admin/", admin.site.urls),
    # Step-up login endpoint: same shape as /api/auth/login/ for
    # non-staff users, but emits an OTP challenge for staff users
    # instead of a JWT. The SPA calls this in place of /api/auth/login/
    # and handles both response shapes.
    path("api/auth/login-step-up/", login_step_up, name="auth-login-step-up"),
    # OTP exchange endpoints.
    path("api/admin-otp/verify/", verify_otp, name="admin-otp-verify"),
    path("api/admin-otp/resend/", resend_otp, name="admin-otp-resend"),
    # REST auth — JWT-based login/logout/registration/password-reset.
    # dj-rest-auth ships a complete set of endpoints under /api/auth/.
    # /api/auth/login/ remains available as a non-step-up login for
    # API clients that haven't migrated to the step-up endpoint yet.
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),
    # allauth — browser-side flows for email confirmation + Google OAuth.
    # The React frontend kicks off Google login by linking the user to
    # /accounts/google/login/, allauth handles the OAuth handshake, then
    # the frontend reads the JWT cookie issued by dj-rest-auth.
    path("accounts/", include("allauth.urls")),
    # Main API.
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
