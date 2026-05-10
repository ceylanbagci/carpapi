from django.conf import settings
from django.conf.urls.static import static
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
            ],
        }
    )


urlpatterns = [
    path("", root),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
