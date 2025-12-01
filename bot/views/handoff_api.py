import logging

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import HumanHandoffRequest, HumanMessage
from ..serializers import (
    HandoffAssignSerializer,
    HandoffResolveSerializer,
    HumanHandoffRequestDetailSerializer,
    HumanHandoffRequestListSerializer,
    HumanHandoffRequestUpdateSerializer,
    HumanMessageCreateSerializer,
    HumanMessageSerializer,
)

logger = logging.getLogger(__name__)


class HumanHandoffRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar solicitudes de handoff humano.

    Endpoints:
    - GET /handoffs/ - Listar handoffs (filtros: status, assigned_to_me)
    - GET /handoffs/{id}/ - Ver detalle de handoff
    - PATCH /handoffs/{id}/ - Actualizar handoff (status, notas)
    - POST /handoffs/{id}/assign/ - Asignarse el handoff
    - POST /handoffs/{id}/resolve/ - Marcar como resuelto
    - GET /handoffs/{id}/messages/ - Ver mensajes
    - POST /handoffs/{id}/messages/ - Enviar mensaje
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filtrar handoffs según rol:
        - STAFF y ADMIN ven todos
        - Usuarios normales no tienen acceso
        """
        from users.models import CustomUser

        user = self.request.user

        # Solo STAFF y ADMIN pueden ver handoffs
        if not (user.is_superuser or user.role in [CustomUser.Role.STAFF, CustomUser.Role.ADMIN]):
            return HumanHandoffRequest.objects.none()

        queryset = HumanHandoffRequest.objects.all().select_related(
            'user', 'anonymous_user', 'assigned_to', 'conversation_log'
        ).prefetch_related('messages')

        # Filtros opcionales
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filtro "assigned_to_me"
        assigned_to_me = self.request.query_params.get('assigned_to_me')
        if assigned_to_me and assigned_to_me.lower() in ['true', '1']:
            queryset = queryset.filter(assigned_to=user)

        # Filtro "unassigned" (pendientes sin asignar)
        unassigned = self.request.query_params.get('unassigned')
        if unassigned and unassigned.lower() in ['true', '1']:
            queryset = queryset.filter(status=HumanHandoffRequest.Status.PENDING, assigned_to__isnull=True)

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        """Usar serializer apropiado según la acción"""
        if self.action == 'list':
            return HumanHandoffRequestListSerializer
        elif self.action in ['update', 'partial_update']:
            return HumanHandoffRequestUpdateSerializer
        elif self.action == 'assign':
            return HandoffAssignSerializer
        elif self.action == 'resolve':
            return HandoffResolveSerializer
        return HumanHandoffRequestDetailSerializer

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """
        Asignar el handoff al usuario actual.

        POST /api/v1/bot/handoffs/{id}/assign/
        """
        handoff = self.get_object()

        # Solo permitir asignar si está PENDING
        if handoff.status != HumanHandoffRequest.Status.PENDING:
            return Response(
                {'error': 'Solo se pueden asignar handoffs en estado PENDING'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Asignar al usuario actual
        handoff.assigned_to = request.user
        handoff.status = HumanHandoffRequest.Status.ASSIGNED
        handoff.assigned_at = timezone.now()
        handoff.save()

        logger.info(
            "Handoff %d asignado a %s",
            handoff.id, request.user.get_full_name()
        )

        serializer = HumanHandoffRequestDetailSerializer(handoff)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """
        Marcar handoff como resuelto.

        POST /api/v1/bot/handoffs/{id}/resolve/
        Body: {"resolution_notes": "..."}
        """
        handoff = self.get_object()
        serializer = HandoffResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Solo permitir resolver si está asignado o en progreso
        if handoff.status not in [HumanHandoffRequest.Status.ASSIGNED, HumanHandoffRequest.Status.IN_PROGRESS]:
            return Response(
                {'error': 'Solo se pueden resolver handoffs asignados o en progreso'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Agregar notas de resolución si se proporcionaron
        resolution_notes = serializer.validated_data.get('resolution_notes')
        if resolution_notes:
            if handoff.internal_notes:
                handoff.internal_notes += f"\n\n--- RESOLUCIÓN ---\n{resolution_notes}"
            else:
                handoff.internal_notes = f"--- RESOLUCIÓN ---\n{resolution_notes}"

        # Marcar como resuelto
        handoff.status = HumanHandoffRequest.Status.RESOLVED
        handoff.resolved_at = timezone.now()
        handoff.save()

        logger.info(
            "Handoff %d marcado como resuelto por %s",
            handoff.id, request.user.get_full_name()
        )

        serializer = HumanHandoffRequestDetailSerializer(handoff)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """
        Listar mensajes del handoff.

        GET /api/v1/bot/handoffs/{id}/messages/
        """
        handoff = self.get_object()
        messages = handoff.messages.all().order_by('created_at')

        # Marcar mensajes del cliente como leídos
        unread_client_messages = messages.filter(is_from_staff=False, read_at__isnull=True)
        for msg in unread_client_messages:
            msg.mark_as_read()

        serializer = HumanMessageSerializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='messages/send')
    def send_message(self, request, pk=None):
        """
        BOT-SEC-HUMAN-CHAT: Enviar mensaje al cliente con validación de ownership.

        POST /api/v1/bot/handoffs/{id}/messages/send/
        Body: {"message": "..."}
        
        Validaciones:
        - Solo el staff asignado o admins pueden responder
        - Se notifica al cliente por email
        - Se registra delivery tracking
        """
        handoff = self.get_object()
        
        # VALIDACIÓN DE OWNERSHIP: Solo el asignado o admins pueden responder
        if handoff.assigned_to and handoff.assigned_to != request.user:
            # Verificar si es admin/superuser
            if not request.user.is_superuser:
                return Response(
                    {
                        'error': 'Solo el staff asignado o administradores pueden responder este handoff',
                        'assigned_to': handoff.assigned_to.get_full_name() if handoff.assigned_to else None
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        # Crear el mensaje
        data = {
            'handoff_request': handoff.id,
            'message': request.data.get('message'),
            'attachments': request.data.get('attachments', [])
        }

        serializer = HumanMessageCreateSerializer(
            data=data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()

        # Si el handoff estaba ASSIGNED, moverlo a IN_PROGRESS
        if handoff.status == HumanHandoffRequest.Status.ASSIGNED:
            handoff.status = HumanHandoffRequest.Status.IN_PROGRESS
            handoff.save()

        logger.info(
            "Mensaje enviado en handoff %d por %s",
            handoff.id, request.user.get_full_name()
        )

        response_serializer = HumanMessageSerializer(message)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
