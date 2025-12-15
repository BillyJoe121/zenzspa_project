from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BotWebhookView, BotHealthCheckView, HumanHandoffRequestViewSet,
    BotAnalyticsView, SuspiciousUsersView, UserActivityTimelineView,
    BlockIPView, UnblockIPView, BotTaskStatusView, WhatsAppWebhookView
)
from .viewsets import BotConfigurationViewSet

# Router para ViewSets
router = DefaultRouter()
router.register(r'handoffs', HumanHandoffRequestViewSet, basename='handoff')
router.register(r'config', BotConfigurationViewSet, basename='bot-config')

urlpatterns = [
    path('webhook/', BotWebhookView.as_view(), name='bot-webhook'),
    path('whatsapp/', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('health/', BotHealthCheckView.as_view(), name='bot-health'),
    path('analytics/', BotAnalyticsView.as_view(), name='bot-analytics'),

    # Endpoints de usuarios sospechosos y bloqueo de IPs
    path('suspicious-users/', SuspiciousUsersView.as_view(), name='suspicious-users'),
    path('activity-timeline/', UserActivityTimelineView.as_view(), name='activity-timeline'),
    path('block-ip/', BlockIPView.as_view(), name='block-ip'),
    path('unblock-ip/', UnblockIPView.as_view(), name='unblock-ip'),

    # Endpoint para verificar estado de tareas asíncronas
    path('task-status/<str:task_id>/', BotTaskStatusView.as_view(), name='task-status'),

    # Incluir rutas del router (handoffs + config)
    path('', include(router.urls)),
]
