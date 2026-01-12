#!/usr/bin/env python3
"""
Script de prueba para enviar un recordatorio de cita por WhatsApp usando Twilio.
Mockea un usuario y una cita y dispara el envío inmediatamente.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import django
from django.utils import timezone

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def build_content_variables(config, context):
    """Adapta el contexto al formato {{1}}, {{2}}, ... que Twilio espera."""
    variables = {}
    for idx, name in enumerate(config.get("variables", []), start=1):
        variables[str(idx)] = str(context.get(name, ""))
    return variables


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiozens.settings")
    django.setup()

    from notifications.twilio_templates import (
        get_template_config,
        is_template_configured,
    )
    from notifications.whatsapp_service import WhatsAppService

    event_code = "APPOINTMENT_REMINDER_24H"
    template_config = get_template_config(event_code)

    if not template_config or not is_template_configured(event_code):
        raise RuntimeError(
            f"El template {event_code} no tiene Content SID configurado. "
            "Actualiza notifications/twilio_templates.py antes de correr esta prueba."
        )

    joseph = SimpleNamespace(
        full_name="Joseph Velez",
        phone_number="+573157589548",
    )
    mocked_appointment_time = timezone.now() + timedelta(hours=24)

    context = {
        "user_name": joseph.full_name,
        "start_date": mocked_appointment_time.strftime("%d %B %Y"),
        "start_time": mocked_appointment_time.strftime("%I:%M %p"),
        "services": "Masaje relajante, Facial express",
        "total": "220.000",
    }

    content_variables = build_content_variables(template_config, context)

    print("Enviando recordatorio de prueba a", joseph.phone_number)
    result = WhatsAppService.send_template_message(
        to_phone=joseph.phone_number,
        content_sid=template_config["content_sid"],
        content_variables=content_variables,
    )

    if not result.get("success"):
        raise RuntimeError(f"El envío falló: {result}")

    print("WhatsApp enviado correctamente. SID:", result["sid"])


if __name__ == "__main__":
    main()
