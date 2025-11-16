from django.urls import path

from .views import BotWebhookView, ActionPreviewView, ActionExecuteView

urlpatterns = [
    path('webhook/', BotWebhookView.as_view(), name='bot-webhook'),
    path('actions/preview/', ActionPreviewView.as_view(), name='bot-action-preview'),
    path('actions/execute/', ActionExecuteView.as_view(), name='bot-action-execute'),
]
