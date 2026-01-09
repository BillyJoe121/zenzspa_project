"""
Django management command para probar notificaciones WhatsApp.

Uso:
    python manage.py test_whatsapp_notifications --phone +573157589548
    python manage.py test_whatsapp_notifications --phone +573157589548 --template APPOINTMENT_REMINDER_24H
    python manage.py test_whatsapp_notifications --list-templates
    python manage.py test_whatsapp_notifications --phone +573157589548 --all --delay 10
"""

import time
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from users.models import CustomUser
from notifications.twilio_templates import TWILIO_TEMPLATE_MAP, is_template_configured
from notifications.whatsapp_service import WhatsAppService
from notifications.services import NotificationService
from notifications.models import NotificationLog


class Command(BaseCommand):
    help = 'Prueba el sistema de notificaciones WhatsApp enviando mensajes de prueba'

    def add_arguments(self, parser):
        parser.add_argument(
            '--phone',
            type=str,
            help='Número de teléfono destino en formato E.164 (ej: +573157589548)'
        )
        parser.add_argument(
            '--template',
            type=str,
            help='Event code del template a probar (ej: APPOINTMENT_REMINDER_24H)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Probar todos los templates configurados'
        )
        parser.add_argument(
            '--list-templates',
            action='store_true',
            help='Listar todos los templates y su estado de configuración'
        )
        parser.add_argument(
            '--delay',
            type=int,
            default=10,
            help='Segundos entre cada envío (default: 10)'
        )
        parser.add_argument(
            '--run-tasks',
            action='store_true',
            help='Ejecutar tareas programadas de Celery manualmente'
        )
        parser.add_argument(
            '--show-logs',
            action='store_true',
            help='Mostrar logs de notificaciones recientes'
        )

    def handle(self, *args, **options):
        if options['list_templates']:
            self.list_templates()
            return

        if options['show_logs']:
            self.show_recent_logs()
            return

        if options['run_tasks']:
            self.run_celery_tasks()
            return

        phone = options.get('phone')
        if not phone:
            raise CommandError('Debes especificar --phone o usar --list-templates')

        # Verificar formato de teléfono
        if not WhatsAppService.validate_phone(phone):
            raise CommandError(f'Número de teléfono inválido: {phone}. Usa formato E.164 (+573157589548)')

        # Obtener o crear usuario de prueba
        user = self.get_or_create_test_user(phone)

        if options['all']:
            self.test_all_templates(user, phone, options['delay'])
        elif options['template']:
            self.test_single_template(user, phone, options['template'])
        else:
            self.stdout.write(self.style.WARNING(
                'Especifica --template <EVENT_CODE>, --all, o --list-templates'
            ))

    def list_templates(self):
        """Lista todos los templates y su estado"""
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('  TEMPLATES DE WHATSAPP'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        configured = []
        not_configured = []

        for event_code, config in TWILIO_TEMPLATE_MAP.items():
            if is_template_configured(event_code):
                configured.append((event_code, config))
            else:
                not_configured.append((event_code, config))

        self.stdout.write(self.style.SUCCESS(f'\n✅ Configurados ({len(configured)}):'))
        for code, config in configured:
            self.stdout.write(f'   - {code}')
            self.stdout.write(f'     {config.get("description", "")}')
            self.stdout.write(f'     SID: {config.get("content_sid", "")}')
            self.stdout.write(f'     Variables: {config.get("variables", [])}')
            self.stdout.write('')

        self.stdout.write(self.style.WARNING(f'\n⚠️ NO configurados ({len(not_configured)}):'))
        for code, config in not_configured:
            self.stdout.write(f'   - {code}: {config.get("description", "")}')

    def get_or_create_test_user(self, phone):
        """Crea o recupera usuario de prueba"""
        user, created = CustomUser.objects.update_or_create(
            phone_number=phone,
            defaults={
                "first_name": "Usuario",
                "last_name": "Prueba",
                "role": CustomUser.Role.CLIENT,
                "is_active": True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Usuario de prueba creado: {phone}'))
        else:
            self.stdout.write(f'Usuario de prueba existente: {phone}')
        return user

    def test_single_template(self, user, phone, event_code):
        """Prueba un template específico"""
        config = TWILIO_TEMPLATE_MAP.get(event_code)
        if not config:
            raise CommandError(f'Template no encontrado: {event_code}')

        if not is_template_configured(event_code):
            raise CommandError(
                f'Template {event_code} no está configurado (SID placeholder). '
                f'Usa --list-templates para ver los disponibles.'
            )

        self.stdout.write(f'\n📤 Enviando template: {event_code}')
        self.stdout.write(f'   {config.get("description", "")}')
        self.stdout.write(f'   SID: {config.get("content_sid", "")}')

        # Obtener contexto de prueba
        context = self.get_test_context(event_code)
        variables = self.map_context_to_variables(config.get("variables", []), context)

        self.stdout.write(f'   Variables: {variables}')

        result = WhatsAppService.send_template_message(
            to_phone=phone,
            content_sid=config["content_sid"],
            content_variables=variables
        )

        if result.get("success"):
            self.stdout.write(self.style.SUCCESS(f'   ✅ Enviado! SID: {result.get("sid")}'))
        else:
            self.stdout.write(self.style.ERROR(f'   ❌ Error: {result.get("error")}'))

    def test_all_templates(self, user, phone, delay):
        """Prueba todos los templates configurados"""
        configured = [
            (code, config) for code, config in TWILIO_TEMPLATE_MAP.items()
            if is_template_configured(code)
        ]

        if not configured:
            raise CommandError('No hay templates configurados para probar')

        self.stdout.write(self.style.SUCCESS(
            f'\n🚀 Probando {len(configured)} templates con {delay}s entre cada uno'
        ))

        for i, (event_code, config) in enumerate(configured, 1):
            self.stdout.write(f'\n[{i}/{len(configured)}] {event_code}')
            self.stdout.write(f'   {config.get("description", "")}')

            context = self.get_test_context(event_code)
            variables = self.map_context_to_variables(config.get("variables", []), context)

            result = WhatsAppService.send_template_message(
                to_phone=phone,
                content_sid=config["content_sid"],
                content_variables=variables
            )

            if result.get("success"):
                self.stdout.write(self.style.SUCCESS(f'   ✅ Enviado! SID: {result.get("sid")}'))
            else:
                self.stdout.write(self.style.ERROR(f'   ❌ Error: {result.get("error")}'))

            if i < len(configured):
                self.stdout.write(f'   ⏳ Esperando {delay}s...')
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS('\n✅ Pruebas completadas'))

    def get_test_context(self, event_code):
        """Obtiene contexto de prueba para cada event_code"""
        contexts = {
            "APPOINTMENT_REMINDER_24H": {
                "user_name": "Usuario Prueba",
                "start_date": "10 de Enero 2026",
                "start_time": "02:00 PM",
                "services": "Masaje Relajante, Facial",
                "total": "150,000",
            },
            "APPOINTMENT_REMINDER_2H": {
                "user_name": "Usuario Prueba",
                "start_time": "02:00 PM",
                "services": "Masaje Relajante",
            },
            "APPOINTMENT_CANCELLED_AUTO": {
                "user_name": "Usuario Prueba",
                "start_date": "10 de Enero 2026",
            },
            "APPOINTMENT_NO_SHOW_CREDIT": {
                "user_name": "Usuario Prueba",
                "start_date": "10 de Enero 2026",
                "credit_amount": "50,000",
            },
            "APPOINTMENT_WAITLIST_AVAILABLE": {
                "user_name": "Usuario Prueba",
                "date": "12 de Enero 2026",
                "time": "03:00 PM",
                "service": "Masaje Terapéutico",
            },
            "VIP_RENEWAL_FAILED": {
                "user_name": "Usuario Prueba",
                "status": "PAST_DUE",
            },
            "VIP_MEMBERSHIP_EXPIRED": {
                "user_name": "Usuario Prueba",
            },
            "VIP_LOYALTY_MILESTONE": {
                "user_name": "Usuario Prueba",
                "visits_count": "10",
                "reward_description": "Masaje gratis por fidelidad",
            },
            "VOUCHER_EXPIRING_SOON": {
                "user_name": "Usuario Prueba",
                "amount": "75,000",
                "expiry_date": "15 de Enero 2026",
                "voucher_code": "VCH-TEST-001",
            },
            "PAYMENT_STATUS_APPROVED": {
                "user_name": "Usuario Prueba",
                "amount": "120,000",
                "reference": "PAY-TEST-001",
                "service": "Masaje Relajante",
            },
            "PAYMENT_STATUS_DECLINED": {
                "user_name": "Usuario Prueba",
                "amount": "120,000",
                "reference": "PAY-TEST-002",
                "decline_reason": "Fondos insuficientes",
            },
            "ORDER_CANCELLED": {
                "user_name": "Usuario Prueba",
                "order_id": "ORD-TEST-001",
                "cancellation_reason": "Producto agotado",
            },
            "ORDER_READY_FOR_PICKUP": {
                "user_name": "Usuario Prueba",
                "order_id": "ORD-TEST-002",
                "store_address": "Calle 123 #45-67, Bogotá",
                "pickup_code": "1234",
            },
            "STOCK_LOW_ALERT": {
                "items_list": "Aceite de Almendras (3 uds), Crema Hidratante (5 uds)",
            },
            "USER_FLAGGED_NON_GRATA": {
                "user_name": "Usuario Problemático",
                "user_email": "test@test.com",
                "user_phone": "+573001234567",
                "flag_reason": "Múltiples no-shows",
                "action_taken": "Bloqueado para reservas",
                "admin_url": "https://studiozens.com/admin",
            },
            "BOT_HANDOFF_CREATED": {
                "score_emoji": "🔴",
                "client_score": "25",
                "client_name": "Cliente Molesto",
                "client_phone": "+573009876543",
                "warning_text": "Cliente requiere atención urgente",
                "escalation_message": "No entiendo el sistema de citas",
                "admin_url": "https://studiozens.com/admin",
            },
            "BOT_HANDOFF_EXPIRED": {
                "handoff_id": "HND-001",
                "client_name": "Cliente Sin Atender",
                "created_at": "2026-01-07 14:00",
                "admin_url": "https://studiozens.com/admin",
            },
            "BOT_SECURITY_ALERT": {
                "alert_type": "RATE_LIMIT_EXCEEDED",
                "user_identifier": "+573001112222",
                "alert_detail": "50 mensajes en 5 minutos",
                "timestamp": "2026-01-07 14:30:00",
            },
        }
        return contexts.get(event_code, {"user_name": "Usuario Prueba"})

    def map_context_to_variables(self, var_names, context):
        """Mapea contexto a formato de variables Twilio {{1}}, {{2}}, etc."""
        variables = {}
        for idx, var_name in enumerate(var_names, start=1):
            value = context.get(var_name, f"[{var_name}]")
            variables[str(idx)] = str(value)
        return variables

    def run_celery_tasks(self):
        """Ejecuta tareas programadas de Celery manualmente"""
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('  EJECUTANDO TAREAS CELERY'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        from spa.tasks import (
            send_appointment_reminder,
            cancel_unpaid_appointments,
            check_vip_loyalty,
            notify_expiring_vouchers,
        )
        from notifications.tasks import (
            check_upcoming_appointments_2h,
        )
        from finances.tasks import (
            check_pending_payments,
            process_recurring_subscriptions,
            downgrade_expired_vips,
        )

        tasks = [
            ("send_appointment_reminder", send_appointment_reminder),
            ("check_upcoming_appointments_2h", check_upcoming_appointments_2h),
            ("cancel_unpaid_appointments", cancel_unpaid_appointments),
            ("check_vip_loyalty", check_vip_loyalty),
            ("notify_expiring_vouchers", notify_expiring_vouchers),
            ("check_pending_payments", check_pending_payments),
            ("process_recurring_subscriptions", process_recurring_subscriptions),
            ("downgrade_expired_vips", downgrade_expired_vips),
        ]

        for name, task in tasks:
            self.stdout.write(f'\n⚙️ {name}')
            try:
                result = task()
                self.stdout.write(self.style.SUCCESS(f'   ✅ {result}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ❌ {str(e)}'))

    def show_recent_logs(self):
        """Muestra logs de notificaciones recientes"""
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('  LOGS DE NOTIFICACIONES RECIENTES'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        recent_logs = NotificationLog.objects.order_by('-created_at')[:20]

        for log in recent_logs:
            status_style = {
                NotificationLog.Status.QUEUED: self.style.WARNING,
                NotificationLog.Status.SENT: self.style.SUCCESS,
                NotificationLog.Status.FAILED: self.style.ERROR,
                NotificationLog.Status.SILENCED: self.style.NOTICE,
            }.get(log.status, self.style.NOTICE)

            user_info = log.user.phone_number if log.user else "Anónimo"
            self.stdout.write(f'\n{status_style(log.status)} [{log.created_at.strftime("%H:%M:%S")}]')
            self.stdout.write(f'   Event: {log.event_code}')
            self.stdout.write(f'   Usuario: {user_info}')
            self.stdout.write(f'   Canal: {log.channel}')
            if log.error_message:
                self.stdout.write(self.style.ERROR(f'   Error: {log.error_message}'))
            if log.sent_at:
                self.stdout.write(f'   Enviado: {log.sent_at}')
