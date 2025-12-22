from django.urls import path
from rag.views import AskView, QueryView

urlpatterns = [
    path("rag/ask/", AskView.as_view(), name="rag-ask"),
    path("rag/query/", QueryView.as_view(), name="rag-query"),
]
