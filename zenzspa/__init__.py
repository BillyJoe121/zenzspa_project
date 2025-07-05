# zenzspa_project/zenzspa/__init__.py

# Esto asegurará que la app de Celery se cargue siempre que Django se inicie.
from .celery import app as celery_app

__all__ = ('celery_app',)
