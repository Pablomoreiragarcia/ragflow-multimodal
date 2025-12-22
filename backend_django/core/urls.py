from django.urls import path, include
from .views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("", include("conversations.urls")),
    path("", include("documents.urls")),
    path("", include("rag.urls")),
]
