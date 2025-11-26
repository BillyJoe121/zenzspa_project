"""
Serializers para el sistema de handoff humano.
"""
from rest_framework import serializers
from .models import HumanHandoffRequest, HumanMessage, AnonymousUser


class AnonymousUserSerializer(serializers.ModelSerializer):
    """Serializer para usuarios anónimos"""
    display_name = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = AnonymousUser
        fields = [
            'id', 'session_id', 'display_name', 'name', 'email',
            'phone_number', 'created_at', 'last_activity', 'is_expired'
        ]
        read_only_fields = ['session_id', 'created_at', 'last_activity']


class HumanMessageSerializer(serializers.ModelSerializer):
    """Serializer para mensajes humanos"""
    sender_name = serializers.ReadOnlyField()
    is_unread = serializers.ReadOnlyField()

    class Meta:
        model = HumanMessage
        fields = [
            'id', 'handoff_request', 'sender', 'sender_name',
            'is_from_staff', 'from_anonymous', 'message',
            'created_at', 'read_at', 'is_unread', 'attachments'
        ]
        read_only_fields = ['created_at', 'read_at', 'sender_name', 'is_unread']

    def validate(self, attrs):
        """Validación personalizada"""
        # Si es del staff, debe tener sender
        if attrs.get('is_from_staff') and not attrs.get('sender'):
            raise serializers.ValidationError(
                "Los mensajes del staff deben tener un sender"
            )
        return attrs


class HumanMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear mensajes (simplificado)"""

    class Meta:
        model = HumanMessage
        fields = ['handoff_request', 'message', 'attachments']

    def create(self, validated_data):
        """Crear mensaje automáticamente asignando sender y flags"""
        request = self.context.get('request')

        # Determinar si es del staff basado en el usuario autenticado
        if request and request.user.is_authenticated:
            validated_data['sender'] = request.user
            validated_data['is_from_staff'] = True
            validated_data['from_anonymous'] = False
        else:
            # Mensaje de cliente anónimo
            validated_data['sender'] = None
            validated_data['is_from_staff'] = False
            validated_data['from_anonymous'] = True

        return super().create(validated_data)


class HumanHandoffRequestListSerializer(serializers.ModelSerializer):
    """Serializer para listar handoff requests (vista resumida)"""
    client_identifier = serializers.ReadOnlyField()
    client_contact_info = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    response_time = serializers.ReadOnlyField()
    escalation_reason_display = serializers.CharField(
        source='get_escalation_reason_display', read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )
    unread_messages_count = serializers.SerializerMethodField()

    class Meta:
        model = HumanHandoffRequest
        fields = [
            'id', 'client_identifier', 'client_score', 'escalation_reason',
            'escalation_reason_display', 'status', 'status_display',
            'assigned_to', 'created_at', 'is_active', 'response_time',
            'client_contact_info', 'unread_messages_count'
        ]

    def get_unread_messages_count(self, obj):
        """Cuenta mensajes no leídos del cliente"""
        return obj.messages.filter(read_at__isnull=True, is_from_staff=False).count()


class HumanHandoffRequestDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado para handoff requests"""
    client_identifier = serializers.ReadOnlyField()
    client_contact_info = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    response_time = serializers.ReadOnlyField()
    resolution_time = serializers.ReadOnlyField()
    escalation_reason_display = serializers.CharField(
        source='get_escalation_reason_display', read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )
    messages = HumanMessageSerializer(many=True, read_only=True)
    anonymous_user_details = AnonymousUserSerializer(source='anonymous_user', read_only=True)

    class Meta:
        model = HumanHandoffRequest
        fields = [
            'id', 'user', 'anonymous_user', 'anonymous_user_details',
            'client_identifier', 'client_score', 'client_contact_info',
            'escalation_reason', 'escalation_reason_display',
            'status', 'status_display', 'assigned_to', 'assigned_at',
            'resolved_at', 'created_at', 'conversation_context',
            'client_interests', 'internal_notes', 'conversation_log',
            'is_active', 'response_time', 'resolution_time', 'messages'
        ]
        read_only_fields = [
            'user', 'anonymous_user', 'client_score', 'escalation_reason',
            'conversation_context', 'client_interests', 'conversation_log',
            'created_at', 'assigned_at', 'resolved_at'
        ]


class HumanHandoffRequestUpdateSerializer(serializers.ModelSerializer):
    """Serializer para actualizar handoff requests"""

    class Meta:
        model = HumanHandoffRequest
        fields = ['status', 'assigned_to', 'internal_notes']

    def update(self, instance, validated_data):
        """Actualizar timestamps automáticamente"""
        from django.utils import timezone

        # Si se está asignando por primera vez
        if 'assigned_to' in validated_data and not instance.assigned_at:
            instance.assigned_at = timezone.now()
            # Cambiar status a ASSIGNED si estaba PENDING
            if instance.status == HumanHandoffRequest.Status.PENDING:
                instance.status = HumanHandoffRequest.Status.ASSIGNED

        # Si se está marcando como resuelto
        if validated_data.get('status') == HumanHandoffRequest.Status.RESOLVED:
            if not instance.resolved_at:
                instance.resolved_at = timezone.now()

        return super().update(instance, validated_data)


class HandoffAssignSerializer(serializers.Serializer):
    """Serializer para asignar handoff al usuario actual"""
    # No necesita campos, usa el usuario del request


class HandoffResolveSerializer(serializers.Serializer):
    """Serializer para marcar handoff como resuelto"""
    resolution_notes = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Notas opcionales sobre la resolución"
    )
