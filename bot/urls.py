from django.urls import path

from .views import BotWebhookView

urlpatterns = [
    path('webhook/', BotWebhookView.as_view(), name='bot-webhook'),
]
