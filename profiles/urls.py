# Crea el archivo zenzspa_project/profiles/urls.py con este contenido

from django.urls import path
from .views import UserProfileDetailView

urlpatterns = [
    path('users/<str:phone_number>/profile/',
         UserProfileDetailView.as_view(), name='user-profile-detail'),
]
