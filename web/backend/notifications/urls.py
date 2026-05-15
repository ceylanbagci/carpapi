from django.urls import path

from .views import PreferencesView, SendTestView

app_name = "notifications"

urlpatterns = [
    path("preferences/", PreferencesView.as_view(), name="preferences"),
    path("test/", SendTestView.as_view(), name="test"),
]
