# backend_django/core/urls.py

from django.urls import path, include
from .views import HealthView
from documents.download_views import TableDownloadView, ImageDownloadView
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("tables/download/", TableDownloadView.as_view(), name="tables-download"),
    path("images/download/", ImageDownloadView.as_view(), name="images-download"),
    path("", include("conversations.urls")),
    path("", include("documents.urls")),
    path("", include("rag.urls")),
]
