# backend_django\conversations\urls.py

from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet

router = DefaultRouter()
router.register(r"conversations", ConversationViewSet, basename="conversations")

urlpatterns = router.urls
