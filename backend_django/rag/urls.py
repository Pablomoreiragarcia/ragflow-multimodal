# backend_django/rag/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from conversations.views import ConversationViewSet
from .views import AskView, ModelsView

router = DefaultRouter()
router.register(r"conversations", ConversationViewSet, basename="conversations")

urlpatterns = [
    path("", include(router.urls)),
    path("rag/ask/", AskView.as_view(), name="rag-ask"),
    path("rag/models/", ModelsView.as_view(), name="rag-models"),
]
