from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from . import views_agents

router = DefaultRouter()
router.register(r"dealers", views.DealerViewSet, basename="dealer")
router.register(r"listings", views.ListingViewSet, basename="listing")

urlpatterns = [
    # No-dependency liveness probe for App Runner / ECS / k8s health
    # checks. Returns 200 OK without touching the DB or Bedrock so it
    # always succeeds as long as gunicorn is up.
    path("healthz/", views.healthz, name="healthz"),
    path("stats/", views.stats, name="stats"),
    path("cars/", views.cars, name="cars"),
    path("makes/", views.makes, name="makes"),
    path("models/", views.models_list, name="models"),
    # RAG-backed chat. POST { "message": "..." } -> { answer, listings, ... }
    # Implementation lives in carpapi/rag/answer.py; this is a thin HTTP shim.
    path("chat/", views.chat, name="chat"),
    # Autonomous-agent fleet status. Merges the 14-agent static roster
    # with live Lambda + EventBridge + CloudWatch data. Implementation
    # in api/views_agents.py.
    path("agents/", views_agents.agents_overview, name="agents-overview"),
    path("", include(router.urls)),
]
