from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from rest_framework import serializers

from .models import GlobalSettings


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    ModelSerializer que oculta campos dinámicamente según el rol del usuario.

    Cómo funciona:
      - Define en Meta.role_based_fields un dict {ROL: [campos]} indicando
        qué campos SOLO están visibles para ese rol (y roles superiores).
      - La jerarquía es: CLIENT < VIP < STAFF < ADMIN.
      - Si el request no existe o el usuario no está autenticado, se asume CLIENT.

    También respeta, si se proveen en context:
      - context['include_fields']: lista blanca explícita de campos a mantener.
      - context['exclude_fields']: lista negra explícita de campos a remover.
    """

    ROLE_HIERARCHY: Dict[str, Sequence[str]] = {
        "CLIENT": ("CLIENT",),
        "VIP": ("CLIENT", "VIP"),
        "STAFF": ("CLIENT", "VIP", "STAFF"),
        "ADMIN": ("CLIENT", "VIP", "STAFF", "ADMIN"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        user_role = getattr(getattr(request, "user", None), "role", "CLIENT") or "CLIENT"
        allowed_roles = set(self.ROLE_HIERARCHY.get(user_role, ("CLIENT",)))

        # Listas de control opcionales desde el contexto
        include_fields: Optional[Iterable[str]] = self.context.get("include_fields")
        exclude_fields: Optional[Iterable[str]] = self.context.get("exclude_fields")

        # 1) Aplica include_fields si está definida (lista blanca)
        if include_fields:
            include_set = set(include_fields)
            for field_name in list(self.fields.keys()):
                if field_name not in include_set:
                    self.fields.pop(field_name, None)

        # 2) Aplica exclude_fields explícitos
        if exclude_fields:
            for field_name in exclude_fields:
                self.fields.pop(field_name, None)

        # 3) Aplica visibilidad por rol definida en el Meta del hijo
        role_config: Dict[str, List[str]] = getattr(self.Meta, "role_based_fields", {})  # type: ignore[attr-defined]
        if role_config:
            # Si el usuario NO tiene un rol requerido para ver ciertos campos, se ocultan
            for required_role, fields in role_config.items():
                if required_role not in allowed_roles:
                    for field_name in fields:
                        self.fields.pop(field_name, None)


class ReadOnlyModelSerializer(serializers.ModelSerializer):
    """
    ModelSerializer de solo lectura.
    Útil para endpoints de listado/detalle donde no se permite modificación.
    
    Ejemplo:
        class UserListSerializer(ReadOnlyModelSerializer):
            class Meta:
                model = User
                fields = ['id', 'name', 'email']
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Marcar todos los campos como read_only
        for field in self.fields.values():
            field.read_only = True


class DataMaskingMixin:
    """
    Proporciona enmascaramiento sistemático de campos sensibles basado en roles.

    Los serializers que lo usen deben definir en su Meta:
        mask_fields = {
            "phone_number": {"mask_with": "phone", "visible_for": ["STAFF"]},
            "email": {"mask_with": "email", "visible_for": ["STAFF"]},
        }
    """

    ROLE_PRIORITY: Dict[str, int] = {
        "CLIENT": 0,
        "VIP": 1,
        "STAFF": 2,
        "ADMIN": 3,
    }
    MASKERS: Dict[str, Callable[[Any], Any]] = {}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        mask_config = self._get_masking_config()
        if not mask_config:
            return data

        viewer = self._get_viewer()
        for field_name, config in mask_config.items():
            if field_name not in data:
                continue
            if not self._should_mask_field(field_name, config, viewer, instance):
                continue
            data[field_name] = self._mask_value(data[field_name], config)
        return data

    def _get_masking_config(self):
        meta = getattr(self, "Meta", None)
        return getattr(meta, "mask_fields", {})

    def _get_viewer(self):
        request = self.context.get("request") if hasattr(self, "context") else None
        return getattr(request, "user", None) if request else None

    def _should_mask_field(self, field_name, config, viewer, instance):
        return not self._viewer_has_clearance(viewer, config)

    def _viewer_has_clearance(self, viewer, config) -> bool:
        visible_for = config.get("visible_for") or config.get("roles") or []
        if not visible_for:
            return False

        viewer_role = getattr(viewer, "role", "CLIENT") or "CLIENT"
        viewer_rank = self.ROLE_PRIORITY.get(viewer_role, 0)
        for role in visible_for:
            required_rank = self.ROLE_PRIORITY.get(role, 0)
            if viewer_rank >= required_rank:
                return True
        return False

    def _mask_value(self, value, config):
        if value in (None, ""):
            return value

        mask_with = config.get("mask_with", "default")
        if callable(mask_with):
            return mask_with(value)

        masker = self._get_masker(mask_with)
        return masker(value)

    def _get_masker(self, mask_with: str) -> Callable[[Any], Any]:
        if not self.MASKERS:
            self.MASKERS = {
                "default": self._mask_default,
                "phone": self._mask_phone,
                "email": self._mask_email,
            }
        return self.MASKERS.get(mask_with, self._mask_default)

    @staticmethod
    def _mask_default(value):
        return "***" if isinstance(value, str) else "***"

    @staticmethod
    def _mask_phone(value):
        string_value = str(value)
        if len(string_value) < 6:
            return "****"
        return f"{string_value[:3]}****{string_value[-2:]}"

    @staticmethod
    def _mask_email(value):
        string_value = str(value)
        if "@" not in string_value:
            return "***"
        local, domain = string_value.split("@", 1)
        if len(local) <= 2:
            masked_local = "***"
        else:
            masked_local = f"{local[0]}***{local[-1]}"
        return f"{masked_local}@{domain}"


class GlobalSettingsSerializer(ReadOnlyModelSerializer):
    """
    Serializer completo de solo lectura para GlobalSettings.

    Expone todos los campos relevantes del modelo de configuración global
    para que puedan ser consultados por el frontend y otros servicios.

    Los campos sensibles (comisiones, pagos al desarrollador) se ocultan
    para usuarios no-ADMIN mediante role_based_fields.
    """

    # Campo calculado para mostrar el nombre legible de la política de crédito
    no_show_credit_policy_display = serializers.CharField(
        source='get_no_show_credit_policy_display',
        read_only=True
    )

    # Información del servicio de recompensa VIP
    loyalty_voucher_service_name = serializers.CharField(
        source='loyalty_voucher_service.name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = GlobalSettings
        fields = [
            # Identificación
            'id',
            'created_at',
            'updated_at',

            # Capacidad y programación
            'low_supervision_capacity',
            'appointment_buffer_time',
            'timezone_display',

            # Política de pagos y anticipos
            'advance_payment_percentage',
            'advance_expiration_minutes',

            # Membresía VIP
            'vip_monthly_price',
            'loyalty_months_required',
            'vip_loyalty_credit_reward',
            'loyalty_voucher_service',

            'loyalty_voucher_service_name',
            'vip_discount_percentage',
            'vip_cashback_percentage',

            # Créditos y devoluciones
            'credit_expiration_days',
            'return_window_days',
            'no_show_credit_policy',
            'no_show_credit_policy_display',

            # Lista de espera
            'waitlist_enabled',
            'waitlist_ttl_minutes',

            # Notificaciones
            'quiet_hours_start',
            'quiet_hours_end',

            # Comisiones del desarrollador (solo ADMIN)
            'developer_commission_percentage',
            'developer_payout_threshold',
            'developer_in_default',
            'developer_default_since',
        ]

        # Campos sensibles solo visibles para ADMIN
        role_based_fields = {
            'ADMIN': [
                'developer_commission_percentage',
                'developer_payout_threshold',
                'developer_in_default',
                'developer_default_since',
            ]
        }


class GlobalSettingsUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para actualizar GlobalSettings.
    
    Permite modificar todos los campos excepto los de auditoría (id, created_at, updated_at).
    Incluye validaciones personalizadas para garantizar consistencia.
    """
    
    class Meta:
        model = GlobalSettings
        fields = [
            # Capacidad y programación
            'low_supervision_capacity',
            'appointment_buffer_time',
            'timezone_display',

            # Política de pagos y anticipos
            'advance_payment_percentage',
            'advance_expiration_minutes',

            # Membresía VIP
            'vip_monthly_price',
            'loyalty_months_required',
            'vip_loyalty_credit_reward',
            'loyalty_voucher_service',
            'vip_discount_percentage',
            'vip_cashback_percentage',

            # Créditos y devoluciones
            'credit_expiration_days',
            'return_window_days',
            'no_show_credit_policy',

            # Lista de espera
            'waitlist_enabled',
            'waitlist_ttl_minutes',

            # Notificaciones
            'quiet_hours_start',
            'quiet_hours_end',

            # Comisiones del desarrollador (solo ADMIN puede modificar)
            'developer_commission_percentage',
            'developer_payout_threshold',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """
        Validaciones adicionales a nivel de serializer.
        """
        # Validar que quiet_hours_start sea menor que quiet_hours_end si ambos están presentes
        quiet_start = data.get('quiet_hours_start')
        quiet_end = data.get('quiet_hours_end')
        
        if quiet_start and quiet_end and quiet_start >= quiet_end:
            raise serializers.ValidationError({
                'quiet_hours_start': 'La hora de inicio debe ser menor que la hora de fin.'
            })
            
        # Validar porcentaje VIP
        vip_pct = data.get('vip_discount_percentage')
        if vip_pct is not None:
             if vip_pct < 0 or vip_pct > 100:
                 raise serializers.ValidationError({
                     'vip_discount_percentage': 'El porcentaje debe estar entre 0 y 100.'
                 })
                 
        # Validar porcentaje Cashback
        cashback_pct = data.get('vip_cashback_percentage')
        if cashback_pct is not None:
             if cashback_pct < 0 or cashback_pct > 100:
                 raise serializers.ValidationError({
                     'vip_cashback_percentage': 'El porcentaje de cashback debe estar entre 0 y 100.'
                 })
        
        return data
    
    def update(self, instance, validated_data):
        """
        Actualiza la instancia con los datos validados.
        El método save() del modelo se encarga de las validaciones adicionales.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance
