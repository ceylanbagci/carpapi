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


urlpatterns = [
    path("", root),
    # Django admin — staff-only management UI.
    path("admin/", admin.site.urls),
    # REST auth — JWT-based login/logout/registration/password-reset.
    # dj-rest-auth ships a complete set of endpoints under /api/auth/.
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
