# Crea el archivo zenzspa_project/profiles/urls.py con este contenido

from django.urls import path
from .views import ClinicalProfileDetailView

urlpatterns = [
        path('<str:phone_number>/', ClinicalProfileDetailView.as_view(), name='profile-detail'),
]
