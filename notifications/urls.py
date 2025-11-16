from django.urls import path

from .views import NotificationPreferenceView

urlpatterns = [
    path('preferences/me/', NotificationPreferenceView.as_view(), name='notification-preferences-me'),
]
