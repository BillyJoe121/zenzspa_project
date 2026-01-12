"""
Script de prueba completo para verificar notificaciones WhatsApp.
Ejecuta las tareas programadas de Celery en secuencia y dispara eventos
que generan notificaciones automáticas.

Uso:
    docker compose exec web python scripts/test_notifications_complete.py

O dentro del contenedor:
    python scripts/test_notifications_complete.py
"""

import os
import sys
import time
import django
from datetime import timedelta
from functools import wraps

# Add project root to sys.path
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from django.utils import timezone
from django.db import transaction

# Import models
from users.models import CustomUser
from spa.models import Appointment, Service, WaitlistEntry
from finances.models import Payment, ClientCredit
from notifications.models import NotificationLog, NotificationTemplate
from notifications.twilio_templates import TWILIO_TEMPLATE_MAP, is_template_configured
from core.models import GlobalSettings

# Import services
from notifications.services import NotificationService
from notifications.whatsapp_service import WhatsAppService

# CONFIGURACIÓN DE PRUEBA
TEST_PHONE = "+573157589548"
TEST_EMAIL = "test_notifications@studiozens.com"
DELAY_BETWEEN_TESTS = 10  # segundos entre cada notificación


def log_section(title):
    """Imprime un separador de sección"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def log_test(func):
    """Decorador para logging de tests"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"\n🧪 Ejecutando: {func.__doc__ or func.__name__}")
        try:
            result = func(*args, **kwargs)
            print(f"   ✅ Completado")
            return result
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    return wrapper


def wait_between_tests():
    """Espera entre tests para evitar rate limiting"""
    print(f"   ⏳ Esperando {DELAY_BETWEEN_TESTS}s antes del siguiente test...")
    time.sleep(DELAY_BETWEEN_TESTS)


def get_or_create_test_user():
    """Crea o recupera el usuario de prueba"""
    user, created = CustomUser.objects.update_or_create(
        phone_number=TEST_PHONE,
        defaults={
            "email": TEST_EMAIL,
            "first_name": "Usuario",
            "last_name": "Prueba",
            "role": CustomUser.Role.CLIENT,
            "is_active": True,
        }
    )
    if created:
        print(f"   📱 Usuario de prueba creado: {user.phone_number}")
    else:
        print(f"   📱 Usuario de prueba existente: {user.phone_number}")
    return user


def check_configured_templates():
    """Verifica qué templates están configurados con SIDs reales"""
    log_section("TEMPLATES DE WHATSAPP CONFIGURADOS")
    
    configured = []
    not_configured = []
    
    for event_code, config in TWILIO_TEMPLATE_MAP.items():
        content_sid = config.get("content_sid", "")
        if is_template_configured(event_code):
            configured.append((event_code, config.get("description", ""), content_sid))
        else:
            not_configured.append((event_code, config.get("description", ""), content_sid))
    
    print(f"\n✅ Templates configurados ({len(configured)}):")
    for code, desc, sid in configured:
        print(f"   - {code}: {desc}")
        print(f"     SID: {sid}")
    
    print(f"\n⚠️ Templates NO configurados ({len(not_configured)}):")
    for code, desc, sid in not_configured:
        print(f"   - {code}: {desc}")
    
    return configured, not_configured


@log_test
def test_direct_template_send(user, event_code, variables):
    """Envío directo de template sin pasar por NotificationService"""
    config = TWILIO_TEMPLATE_MAP.get(event_code)
    if not config:
        print(f"   ⚠️ No hay configuración para {event_code}")
        return None
    
    content_sid = config["content_sid"]
    var_names = config.get("variables", [])
    
    # Mapear variables a formato numérico {{1}}, {{2}}, etc.
    content_variables = {}
    for idx, var_name in enumerate(var_names, start=1):
        value = variables.get(var_name, f"[{var_name}]")
        content_variables[str(idx)] = str(value)
    
    print(f"   📤 Enviando template: {event_code}")
    print(f"   📤 Content SID: {content_sid}")
    print(f"   📤 Variables: {content_variables}")
    
    result = WhatsAppService.send_template_message(
        to_phone=TEST_PHONE,
        content_sid=content_sid,
        content_variables=content_variables
    )
    
    if result.get("success"):
        print(f"   ✅ Mensaje enviado! SID: {result.get('sid')}")
    else:
        print(f"   ❌ Error: {result.get('error')}")
    
    return result


@log_test
def test_notification_service(user, event_code, context):
    """Envío a través de NotificationService (sistema real)"""
    print(f"   📤 Enviando via NotificationService: {event_code}")
    print(f"   📤 Context: {context}")
    
    log = NotificationService.send_notification(
        user=user,
        event_code=event_code,
        context=context,
        priority="critical"  # Saltarse quiet hours
    )
    
    if log:
        print(f"   📋 NotificationLog ID: {log.id}")
        print(f"   📋 Status: {log.status}")
    else:
        print(f"   ⚠️ No se creó NotificationLog (posible template faltante)")
    
    return log


def run_all_template_tests(user, configured_templates):
    """Ejecuta tests de todos los templates configurados"""
    log_section("PRUEBAS DE TEMPLATES INDIVIDUALES")
    
    test_contexts = {
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
    
    results = []
    for event_code, description, sid in configured_templates:
        context = test_contexts.get(event_code, {"user_name": "Usuario Prueba"})
        print(f"\n{'─' * 40}")
        print(f"📧 Testing: {event_code}")
        print(f"   {description}")
        
        # Usamos envío directo para mayor control
        result = test_direct_template_send(user, event_code, context)
        results.append((event_code, result))
        
        wait_between_tests()
    
    return results


def run_celery_task_tests():
    """Ejecuta las tareas programadas de Celery manualmente"""
    log_section("PRUEBAS DE TAREAS CELERY PROGRAMADAS")
    
    # Importar las tareas
    from spa.tasks import (
        send_appointment_reminder,
        cancel_unpaid_appointments,
        check_vip_loyalty,
        notify_expiring_vouchers,
    )
    from notifications.tasks import (
        check_upcoming_appointments_2h,
        cleanup_old_notification_logs,
    )
    from finances.tasks import (
        check_pending_payments,
        process_recurring_subscriptions,
        downgrade_expired_vips,
    )
    
    tasks = [
        ("send_appointment_reminder", send_appointment_reminder, 
         "Envía recordatorios 24h antes de citas"),
        ("check_upcoming_appointments_2h", check_upcoming_appointments_2h,
         "Envía recordatorios 2h antes de citas"),
        ("cancel_unpaid_appointments", cancel_unpaid_appointments,
         "Cancela citas sin pago y notifica"),
        ("check_vip_loyalty", check_vip_loyalty,
         "Otorga recompensas VIP por fidelidad"),
        ("notify_expiring_vouchers", notify_expiring_vouchers,
         "Notifica vouchers próximos a expirar"),
        ("check_pending_payments", check_pending_payments,
         "Verifica pagos pendientes"),
        ("process_recurring_subscriptions", process_recurring_subscriptions,
         "Procesa renovaciones VIP automáticas"),
        ("downgrade_expired_vips", downgrade_expired_vips,
         "Degrada VIPs expirados y notifica"),
    ]
    
    for name, task, description in tasks:
        print(f"\n{'─' * 40}")
        print(f"⚙️ Tarea: {name}")
        print(f"   {description}")
        try:
            result = task()  # Ejecutar sincrónicamente
            print(f"   ✅ Resultado: {result}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        time.sleep(2)  # Pequeña pausa entre tareas


def create_test_appointment_for_reminders(user):
    """Crea una cita de prueba que dispare recordatorios"""
    log_section("CREANDO CITA DE PRUEBA PARA RECORDATORIOS")
    
    # Buscar o crear un servicio de prueba
    service, _ = Service.objects.get_or_create(
        name="Servicio de Prueba",
        defaults={
            "price": 50000,
            "duration": timedelta(minutes=60),
            "description": "Servicio para pruebas de notificaciones",
            "is_active": True,
        }
    )
    
    # Crear cita para dentro de ~24 horas (para que el reminder_24h la detecte)
    now = timezone.now()
    
    # Cita para 24h
    start_24h = now + timedelta(hours=24, minutes=30)
    appt_24h, created = Appointment.objects.get_or_create(
        user=user,
        start_time=start_24h,
        defaults={
            "end_time": start_24h + timedelta(hours=1),
            "status": Appointment.AppointmentStatus.CONFIRMED,
            "total": 50000,
        }
    )
    if created:
        appt_24h.services.add(service)
        print(f"   📅 Cita 24h creada: {appt_24h.id} para {start_24h}")
    else:
        print(f"   📅 Cita 24h existente: {appt_24h.id}")
    
    # Cita para 2h
    start_2h = now + timedelta(hours=2, minutes=3)
    appt_2h, created = Appointment.objects.get_or_create(
        user=user,
        start_time=start_2h,
        defaults={
            "end_time": start_2h + timedelta(hours=1),
            "status": Appointment.AppointmentStatus.CONFIRMED,
            "total": 50000,
        }
    )
    if created:
        appt_2h.services.add(service)
        print(f"   📅 Cita 2h creada: {appt_2h.id} para {start_2h}")
    else:
        print(f"   📅 Cita 2h existente: {appt_2h.id}")
    
    return appt_24h, appt_2h


def show_recent_notification_logs():
    """Muestra los logs de notificaciones recientes"""
    log_section("LOGS DE NOTIFICACIONES RECIENTES")
    
    recent_logs = NotificationLog.objects.order_by('-created_at')[:20]
    
    for log in recent_logs:
        status_emoji = {
            NotificationLog.Status.QUEUED: "🔄",
            NotificationLog.Status.SENT: "✅",
            NotificationLog.Status.FAILED: "❌",
            NotificationLog.Status.SILENCED: "🔇",
        }.get(log.status, "❓")
        
        user_info = log.user.phone_number if log.user else "Anónimo"
        print(f"{status_emoji} [{log.created_at.strftime('%H:%M:%S')}] {log.event_code}")
        print(f"   Usuario: {user_info}")
        print(f"   Canal: {log.channel}")
        print(f"   Status: {log.status}")
        if log.error_message:
            print(f"   Error: {log.error_message}")
        if log.sent_at:
            print(f"   Enviado: {log.sent_at}")
        print()


def interactive_menu():
    """Menú interactivo para seleccionar pruebas"""
    while True:
        log_section("MENÚ DE PRUEBAS")
        print("1. Ver templates configurados")
        print("2. Probar TODOS los templates configurados (10s entre cada uno)")
        print("3. Probar UN template específico")
        print("4. Ejecutar tareas programadas de Celery")
        print("5. Crear citas de prueba para recordatorios")
        print("6. Ver logs de notificaciones recientes")
        print("7. Ejecutar prueba completa (todo)")
        print("0. Salir")
        print()
        
        choice = input("Selecciona una opción: ").strip()
        
        if choice == "0":
            print("\n👋 ¡Hasta luego!")
            break
        
        user = get_or_create_test_user()
        
        if choice == "1":
            check_configured_templates()
        
        elif choice == "2":
            configured, _ = check_configured_templates()
            if configured:
                confirm = input(f"\n¿Enviar {len(configured)} mensajes a {TEST_PHONE}? (s/n): ")
                if confirm.lower() == 's':
                    run_all_template_tests(user, configured)
            else:
                print("\n⚠️ No hay templates configurados")
        
        elif choice == "3":
            configured, _ = check_configured_templates()
            if configured:
                print("\nTemplates disponibles:")
                for i, (code, desc, _) in enumerate(configured, 1):
                    print(f"  {i}. {code}")
                
                try:
                    idx = int(input("\nNúmero del template: ")) - 1
                    if 0 <= idx < len(configured):
                        event_code = configured[idx][0]
                        # Usar contexto de prueba
                        test_contexts = {
                            "APPOINTMENT_REMINDER_24H": {
                                "user_name": "Usuario Prueba",
                                "start_date": "10 de Enero 2026",
                                "start_time": "02:00 PM",
                                "services": "Masaje Relajante",
                                "total": "150,000",
                            },
                            "APPOINTMENT_REMINDER_2H": {
                                "user_name": "Usuario Prueba",
                                "start_time": "02:00 PM",
                                "services": "Masaje Relajante",
                            },
                        }
                        context = test_contexts.get(event_code, {"user_name": "Usuario Prueba"})
                        test_direct_template_send(user, event_code, context)
                except (ValueError, IndexError):
                    print("❌ Opción inválida")
        
        elif choice == "4":
            run_celery_task_tests()
        
        elif choice == "5":
            create_test_appointment_for_reminders(user)
        
        elif choice == "6":
            show_recent_notification_logs()
        
        elif choice == "7":
            print("\n🚀 INICIANDO PRUEBA COMPLETA...")
            configured, _ = check_configured_templates()
            if configured:
                create_test_appointment_for_reminders(user)
                run_celery_task_tests()
                
                confirm = input(f"\n¿Enviar {len(configured)} mensajes directos? (s/n): ")
                if confirm.lower() == 's':
                    run_all_template_tests(user, configured)
                
                show_recent_notification_logs()
        
        input("\nPresiona Enter para continuar...")


def main():
    """Función principal"""
    log_section("PRUEBA DE NOTIFICACIONES WHATSAPP - STUDIOZENS")
    print(f"📱 Número de destino: {TEST_PHONE}")
    print(f"⏱️ Delay entre tests: {DELAY_BETWEEN_TESTS}s")
    print(f"🕐 Hora actual: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Verificar credenciales
    from django.conf import settings
    if not all([
        getattr(settings, 'TWILIO_ACCOUNT_SID', None),
        getattr(settings, 'TWILIO_AUTH_TOKEN', None),
        getattr(settings, 'TWILIO_WHATSAPP_FROM', None)
    ]):
        print("\n❌ ERROR: Credenciales de Twilio no configuradas")
        print("   Asegúrate de tener TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM")
        return
    
    print(f"✅ Credenciales Twilio configuradas")
    print(f"   TWILIO_WHATSAPP_FROM: {settings.TWILIO_WHATSAPP_FROM}")
    
    # Modo interactivo o automático
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        # Modo automático: ejecutar todo
        user = get_or_create_test_user()
        configured, _ = check_configured_templates()
        
        if configured:
            create_test_appointment_for_reminders(user)
            run_celery_task_tests()
            run_all_template_tests(user, configured)
            show_recent_notification_logs()
    else:
        # Modo interactivo
        interactive_menu()


if __name__ == "__main__":
    main()
