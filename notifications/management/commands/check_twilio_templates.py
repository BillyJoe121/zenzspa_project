"""
Comando para verificar el estado de configuracion de templates de Twilio.
Uso: python manage.py check_twilio_templates
"""
from django.core.management.base import BaseCommand
from notifications.twilio_templates import (
    TWILIO_TEMPLATE_MAP,
    get_all_event_codes,
    is_template_configured,
)


class Command(BaseCommand):
    help = 'Verifica el estado de configuracion de templates de Twilio/Meta'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== ESTADO DE TEMPLATES DE WHATSAPP ===\n'))
        self.stdout.write('=' * 80)

        total = len(TWILIO_TEMPLATE_MAP)
        configured = 0
        pending = 0

        # Tabla de templates
        self.stdout.write(f"\n{'Event Code':<40} {'Status':<15} {'Content SID'}")
        self.stdout.write('-' * 80)

        for event_code in get_all_event_codes():
            config = TWILIO_TEMPLATE_MAP[event_code]
            content_sid = config["content_sid"]
            is_ready = is_template_configured(event_code)

            if is_ready:
                status = self.style.SUCCESS("[OK] CONFIGURADO")
                configured += 1
            else:
                status = self.style.WARNING("[--] PENDIENTE")
                pending += 1

            # Truncar SID para mejor visualizacion
            sid_display = content_sid[:32] + "..." if len(content_sid) > 35 else content_sid

            self.stdout.write(f"{event_code:<40} {status:<24} {sid_display}")

        # Resumen
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(f"\n=== RESUMEN:")
        self.stdout.write(f"   Total de templates: {total}")
        self.stdout.write(self.style.SUCCESS(f"   [OK] Configurados: {configured}"))
        self.stdout.write(self.style.WARNING(f"   [--] Pendientes: {pending}"))

        if pending > 0:
            self.stdout.write(self.style.WARNING(
                f"\n[!] Tienes {pending} templates pendientes de configurar."
            ))
            self.stdout.write(
                "\n[*] Instrucciones:\n"
                "   1. Espera a que Meta apruebe tus templates en Twilio\n"
                "   2. Ve a Twilio Console -> Messaging -> Content Templates\n"
                "   3. Copia el Content SID de cada template\n"
                "   4. Actualiza notifications/twilio_templates.py\n"
                "   5. Reemplaza cada HX00000... con el SID real\n"
            )
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n[*] Todos los templates estan configurados!\n"
            ))

        # Advertencia sobre fallback
        if pending > 0:
            self.stdout.write(self.style.WARNING(
                "\n[!] IMPORTANTE:\n"
                "   Mientras los templates no esten configurados, el sistema usara\n"
                "   mensajes dinamicos (free-form). Esto SOLO funciona si el usuario\n"
                "   ha enviado un mensaje en las ultimas 24 horas.\n"
            ))

        self.stdout.write('')
