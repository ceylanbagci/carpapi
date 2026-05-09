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
