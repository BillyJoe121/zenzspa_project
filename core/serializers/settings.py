"""
Core Serializers - GlobalSettings.
"""
from __future__ import annotations

from rest_framework import serializers

from core.models import GlobalSettings
from core.serializers.base import ReadOnlyModelSerializer


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
