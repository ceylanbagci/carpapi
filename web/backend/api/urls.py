from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"dealers", views.DealerViewSet, basename="dealer")
router.register(r"listings", views.ListingViewSet, basename="listing")

urlpatterns = [
    path("stats/", views.stats, name="stats"),
    path("cars/", views.cars, name="cars"),
    path("makes/", views.makes, name="makes"),
    path("models/", views.models_list, name="models"),
    path("", include(router.urls)),
]
