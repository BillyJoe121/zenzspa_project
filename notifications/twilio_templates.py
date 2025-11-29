"""
Mapeo de event_codes a Content SIDs de Twilio.
Actualizar estos SIDs cuando Meta apruebe los templates.

INSTRUCCIONES:
1. Cuando Meta apruebe tus templates, ve a Twilio Console
2. Messaging → Content → Content Templates
3. Click en cada template y copia su Content SID (empieza con HX...)
4. Reemplaza los SIDs de ejemplo abajo con los reales
"""

# Mapeo: event_code → (content_sid, variables_mapping)
TWILIO_TEMPLATE_MAP = {
    # ===== RECORDATORIOS DE CITAS =====
    "APPOINTMENT_REMINDER_24H": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX312e18d0e6d472368178c3755e3f4bb3",
        "variables": ["user_name", "start_date", "start_time", "services", "total"],
        "description": "Recordatorio de cita 24 horas antes",
    },
    "APPOINTMENT_REMINDER_2H": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000002",
        "variables": ["user_name", "start_time", "services"],
        "description": "Recordatorio de cita 2 horas antes",
    },

    # ===== CANCELACIONES DE CITAS =====
    "APPOINTMENT_CANCELLED_AUTO": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000003",
        "variables": ["user_name", "start_time"],
        "description": "Cita cancelada automáticamente por falta de pago",
    },

    # ===== NO-SHOW =====
    "APPOINTMENT_NO_SHOW_CREDIT": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000004",
        "variables": ["user_name", "start_time", "credit_amount"],
        "description": "No-show con crédito generado",
    },


    # ===== LISTA DE ESPERA =====
    "APPOINTMENT_WAITLIST_AVAILABLE": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000006",
        "variables": ["user_name", "date", "time", "service"],
        "description": "Espacio disponible en lista de espera",
    },

    # ===== VIP MEMBERSHIP =====
    "VIP_RENEWAL_FAILED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000007",
        "variables": ["user_name", "failure_reason", "expiry_date"],
        "description": "Error en renovación VIP",
    },
    "VIP_MEMBERSHIP_EXPIRED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000008",
        "variables": ["user_name"],
        "description": "Membresía VIP expirada",
    },
    "VIP_LOYALTY_MILESTONE": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000009",
        "variables": ["user_name", "visits_count", "reward_description"],
        "description": "Logro VIP alcanzado",
    },

    # ===== VOUCHERS =====
    "VOUCHER_EXPIRING_SOON": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000010",
        "variables": ["user_name", "amount", "expiry_date", "voucher_code"],
        "description": "Voucher próximo a expirar",
    },

    # ===== PAGOS =====
    "PAYMENT_STATUS_APPROVED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000011",
        "variables": ["user_name", "amount", "reference", "concept", "extra_info"],
        "description": "Pago aprobado exitosamente",
    },
    "PAYMENT_STATUS_DECLINED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000012",
        "variables": ["user_name", "amount", "reference", "decline_reason"],
        "description": "Pago rechazado",
    },
    "PAYMENT_STATUS_ERROR": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000013",
        "variables": ["user_name", "amount", "reference"],
        "description": "Error procesando pago",
    },

    # ===== ÓRDENES MARKETPLACE =====

    "ORDER_CANCELLED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000016",
        "variables": ["user_name", "order_id", "cancellation_reason", "refund_info"],
        "description": "Orden cancelada",
    },
    "ORDER_READY_FOR_PICKUP": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000017",
        "variables": ["user_name", "order_id", "store_address", "store_hours", "pickup_code"],
        "description": "Orden lista para recoger",
    },

    # ===== DEVOLUCIONES =====

    "ORDER_CREDIT_ISSUED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000020",
        "variables": ["user_name", "credit_amount", "reason", "order_id"],
        "description": "Créditos abonados",
    },

    # ===== ALERTAS DE STOCK (Admin) =====
    "STOCK_LOW_ALERT": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000021",
        "variables": ["items_list"],
        "description": "Alerta de stock bajo",
    },

    # ===== USUARIO PERSONA NON GRATA (Admin) =====
    "USER_FLAGGED_NON_GRATA": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000022",
        "variables": ["user_name", "user_email", "user_phone", "flag_reason", "action_taken", "admin_url"],
        "description": "Usuario marcado como non grata",
    },

    # ===== BOT HANDOFF (Staff/Admin) =====
    "BOT_HANDOFF_CREATED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000023",
        "variables": ["score_emoji", "client_score", "client_name", "client_phone", "warning_text", "escalation_message", "admin_url"],
        "description": "Nueva solicitud de atención humana",
    },
    "BOT_HANDOFF_EXPIRED": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000024",
        "variables": ["handoff_id", "client_name", "created_at", "admin_url"],
        "description": "Handoff sin atender expirado",
    },

    # ===== BOT SECURITY (Admin) =====
    "BOT_SECURITY_ALERT": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000025",
        "variables": ["alert_type", "user_identifier", "alert_detail", "timestamp"],
        "description": "Alerta de seguridad del bot",
    },
    "BOT_AUTO_BLOCK": {
        # TODO: Reemplazar con SID real
        "content_sid": "HX00000000000000000000000000000026",
        "variables": ["user_identifier", "block_reason", "timestamp", "admin_url"],
        "description": "Usuario auto-bloqueado",
    },
}


def get_template_config(event_code):
    """
    Obtiene la configuración del template para un event_code.

    Args:
        event_code: El código del evento (ej: "APPOINTMENT_REMINDER_24H")

    Returns:
        dict con 'content_sid', 'variables', y 'description', o None si no existe
    """
    return TWILIO_TEMPLATE_MAP.get(event_code)


def is_template_configured(event_code):
    """
    Verifica si un event_code tiene template aprobado configurado.

    Args:
        event_code: El código del evento

    Returns:
        bool: True si está configurado con SID real (no HX00000...)
    """
    config = get_template_config(event_code)
    if not config:
        return False

    content_sid = config.get("content_sid", "")
    # Verificar que no sea un SID de ejemplo (HX00000...)
    return content_sid and not content_sid.startswith("HX00000")


def get_all_event_codes():
    """
    Retorna lista de todos los event_codes configurados.

    Returns:
        list: Lista de strings con event_codes
    """
    return list(TWILIO_TEMPLATE_MAP.keys())


def validate_context(event_code, context):
    """
    Valida que el contexto contenga todas las variables requeridas.

    Args:
        event_code: El código del evento
        context: Dict con las variables del contexto

    Returns:
        tuple: (is_valid: bool, missing_variables: list)
    """
    config = get_template_config(event_code)
    if not config:
        return False, ["Template no existe"]

    required_vars = config.get("variables", [])
    missing = [var for var in required_vars if var not in context]

    return len(missing) == 0, missing
