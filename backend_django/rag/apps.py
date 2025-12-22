# backend_django/rag/apps.py
from django.apps import AppConfig

class RagConfig(AppConfig):
    name = "rag"

    def ready(self):
        # No inicializar vectorstores aquí.
        # Se hace vía `python manage.py init_vectorstores`
        return