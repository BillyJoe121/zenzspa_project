"""
ViewSet para gestión de configuración del Bot.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsAdminUser
from .models.config import BotConfiguration
from .serializers_config import BotConfigurationSerializer, BotConfigurationUpdateSerializer


class BotConfigurationViewSet(viewsets.ViewSet):
    """
    ViewSet para gestión de configuración del bot.
    
    Solo permite GET y UPDATE (no DELETE ni CREATE ya que es un singleton).
    Requiere permisos de ADMIN para modificar.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def list(self, request):
        """
        GET /api/v1/bot/config/
        
        Retorna la configuración del bot.
        Solo ADMIN puede ver esta información.
        """
        config = BotConfiguration.objects.first()
        
        if not config:
            # Crear configuración por defecto si no existe
            config = BotConfiguration.objects.create()
        
        serializer = BotConfigurationSerializer(config)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None):
        """
        GET /api/v1/bot/config/{id}/
        
        Retorna la configuración del bot por ID.
        """
        try:
            config = BotConfiguration.objects.get(pk=pk)
        except BotConfiguration.DoesNotExist:
            return Response(
                {'detail': 'Configuración no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = BotConfigurationSerializer(config)
        return Response(serializer.data)
    
    def update(self, request, pk=None):
        """
        PUT /api/v1/bot/config/{id}/
        
        Actualiza la configuración del bot.
        Solo ADMIN puede modificar.
        """
        try:
            config = BotConfiguration.objects.get(pk=pk)
        except BotConfiguration.DoesNotExist:
            return Response(
                {'detail': 'Configuración no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = BotConfigurationUpdateSerializer(
            config,
            data=request.data,
            partial=False
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Retornar la configuración actualizada
        response_serializer = BotConfigurationSerializer(config)
        return Response(response_serializer.data)
    
    def partial_update(self, request, pk=None):
        """
        PATCH /api/v1/bot/config/{id}/
        
        Actualiza parcialmente la configuración del bot.
        Solo ADMIN puede modificar.
        """
        try:
            config = BotConfiguration.objects.get(pk=pk)
        except BotConfiguration.DoesNotExist:
            return Response(
                {'detail': 'Configuración no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = BotConfigurationUpdateSerializer(
            config,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Retornar la configuración actualizada
        response_serializer = BotConfigurationSerializer(config)
        return Response(response_serializer.data)
    
    @action(detail=False, methods=['post'])
    def reset_to_defaults(self, request):
        """
        POST /api/v1/bot/config/reset_to_defaults/
        
        Reinicia la configuración del bot a valores por defecto.
        Solo ADMIN puede ejecutar esta acción.
        """
        config = BotConfiguration.objects.first()
        
        if not config:
            config = BotConfiguration.objects.create()
        else:
            # Reiniciar a defaults
            from .models.config import DEFAULT_SYSTEM_PROMPT
            
            config.site_name = "Studio Zens"
            config.booking_url = "https://www.studiozens.com/agendar"
            config.admin_phone = "+57 0"
            config.system_prompt_template = DEFAULT_SYSTEM_PROMPT
            config.api_input_price_per_1k = 0.0001
            config.api_output_price_per_1k = 0.0004
            config.daily_cost_alert_threshold = 0.33
            config.avg_tokens_alert_threshold = 2000
            config.enable_critical_alerts = True
            config.enable_auto_block = True
            config.auto_block_critical_threshold = 3
            config.auto_block_analysis_period_hours = 24
            config.is_active = True
            
            config.save()
        
        serializer = BotConfigurationSerializer(config)
        return Response({
            'message': 'Configuración del bot reiniciada a valores por defecto',
            'config': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """
        POST /api/v1/bot/config/{id}/toggle_active/
        
        Activa/desactiva el bot.
        """
        try:
            config = BotConfiguration.objects.get(pk=pk)
        except BotConfiguration.DoesNotExist:
            return Response(
                {'detail': 'Configuración no encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        config.is_active = not config.is_active
        config.save()
        
        serializer = BotConfigurationSerializer(config)
        return Response({
            'message': f'Bot {"activado" if config.is_active else "desactivado"}',
            'config': serializer.data
        })
