from django.urls import path

from .views import BotWebhookView, BotHealthCheckView

urlpatterns = [
    path('webhook/', BotWebhookView.as_view(), name='bot-webhook'),
    path('health/', BotHealthCheckView.as_view(), name='bot-health'),  # CORRECCIÓN MODERADA
]
