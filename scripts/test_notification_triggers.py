"""
Script para probar los DISPARADORES reales de notificaciones.
Crea las condiciones necesarias y ejecuta las tareas de Celery
para verificar que el flujo completo funciona.

Uso:
    docker compose exec web python scripts/test_notification_triggers.py
"""

import os
import sys
import time
import django
from datetime import timedelta
from decimal import Decimal

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from django.utils import timezone
from django.db import transaction

# Models
from users.models import CustomUser
from spa.models import Appointment, Service
from finances.models import Payment, ClientCredit
from notifications.models import NotificationLog
from core.models import GlobalSettings

# Configuración
TEST_PHONE = "+573157589548"
TEST_EMAIL = "trigger_test@studiozens.com"


def log_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def get_or_create_test_user():
    """Crea usuario de prueba con el número destino"""
    user, created = CustomUser.objects.update_or_create(
        phone_number=TEST_PHONE,
        defaults={
            "email": TEST_EMAIL,
            "first_name": "Usuario",
            "last_name": "Prueba Trigger",
            "role": CustomUser.Role.CLIENT,
            "is_active": True,
        }
    )
    print(f"{'📱 Usuario creado' if created else '📱 Usuario existente'}: {user.phone_number}")
    return user


def get_or_create_test_service():
    """Crea servicio de prueba"""
    from spa.models import ServiceCategory
    
    # Primero obtener o crear una categoría
    category, _ = ServiceCategory.objects.get_or_create(
        name="Pruebas",
        defaults={"description": "Categoría para pruebas"}
    )
    
    service, _ = Service.objects.get_or_create(
        name="Servicio Prueba Trigger",
        defaults={
            "price": Decimal("75000"),
            "duration": 60,  # Minutos como entero
            "description": "Servicio para pruebas de disparadores",
            "is_active": True,
            "category": category,
        }
    )
    return service


def count_notifications_for_user(user, event_code=None, since=None):
    """Cuenta notificaciones para un usuario"""
    qs = NotificationLog.objects.filter(user=user)
    if event_code:
        qs = qs.filter(event_code=event_code)
    if since:
        qs = qs.filter(created_at__gte=since)
    return qs.count()


def get_recent_notifications(user, limit=5):
    """Obtiene las notificaciones más recientes"""
    return NotificationLog.objects.filter(user=user).order_by('-created_at')[:limit]


def show_notification_result(user, before_count, event_code, task_result):
    """Muestra el resultado de la prueba"""
    after_count = count_notifications_for_user(user, event_code)
    new_notifications = after_count - before_count
    
    print(f"\n   📊 Resultado de la tarea: {task_result}")
    print(f"   📬 Notificaciones '{event_code}' antes: {before_count}")
    print(f"   📬 Notificaciones '{event_code}' después: {after_count}")
    print(f"   📬 Nuevas notificaciones: {new_notifications}")
    
    if new_notifications > 0:
        print("\n   ✅ ¡DISPARADOR FUNCIONÓ!")
        # Mostrar la notificación creada
        latest = NotificationLog.objects.filter(
            user=user, 
            event_code=event_code
        ).order_by('-created_at').first()
        if latest:
            print(f"   📋 Log ID: {latest.id}")
            print(f"   📋 Status: {latest.status}")
            print(f"   📋 Canal: {latest.channel}")
            if latest.sent_at:
                print(f"   📋 Enviado: {latest.sent_at}")
            if latest.error_message:
                print(f"   ⚠️ Error: {latest.error_message}")
    else:
        print("\n   ⚠️ No se generaron nuevas notificaciones")
        print("   (Puede ser normal si no cumple todas las condiciones)")
    
    return new_notifications > 0


# =============================================================================
# PRUEBA 1: Recordatorio de cita 2 horas antes
# =============================================================================
def test_trigger_appointment_reminder_2h():
    """
    Prueba: check_upcoming_appointments_2h
    
    Esta tarea busca citas que empiecen entre 2h y 2h+5min desde ahora
    y envía un recordatorio WhatsApp.
    """
    log_section("PRUEBA: RECORDATORIO 2 HORAS (check_upcoming_appointments_2h)")
    
    from notifications.tasks import check_upcoming_appointments_2h
    
    user = get_or_create_test_user()
    service = get_or_create_test_service()
    
    # La tarea busca citas entre now+2h y now+2h+5min
    now = timezone.now()
    # Crear cita para dentro de 2 horas y 2 minutos (dentro de la ventana)
    start_time = now + timedelta(hours=2, minutes=2)
    end_time = start_time + timedelta(hours=1)
    
    print(f"\n🕐 Hora actual: {now.strftime('%H:%M:%S')}")
    print(f"📅 Creando cita para: {start_time.strftime('%H:%M:%S')} (en ~2h)")
    
    # Limpiar citas de prueba anteriores para este usuario
    Appointment.objects.filter(
        user=user,
        status__in=[
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]
    ).update(status=Appointment.AppointmentStatus.CANCELLED)
    
    # Crear nueva cita
    appointment = Appointment.objects.create(
        user=user,
        start_time=start_time,
        end_time=end_time,
        status=Appointment.AppointmentStatus.CONFIRMED,
        total=Decimal("75000"),
    )
    appointment.services.add(service)
    print(f"✅ Cita creada: {appointment.id}")
    print(f"   Status: {appointment.status}")
    print(f"   Servicios: {appointment.get_service_names()}")
    
    # Contar notificaciones antes
    before_count = count_notifications_for_user(user, "APPOINTMENT_REMINDER_2H")
    
    # Ejecutar la tarea
    print("\n⚙️ Ejecutando tarea: check_upcoming_appointments_2h()")
    result = check_upcoming_appointments_2h()
    
    # Esperar un poco para que Celery procese
    print("   ⏳ Esperando 3s para que se procese...")
    time.sleep(3)
    
    # Verificar resultado
    success = show_notification_result(user, before_count, "APPOINTMENT_REMINDER_2H", result)
    
    return success


# =============================================================================
# PRUEBA 2: Recordatorio de cita 24 horas antes
# =============================================================================
def test_trigger_appointment_reminder_24h():
    """
    Prueba: send_appointment_reminder
    
    Esta tarea busca citas que empiecen entre 24h y 25h desde ahora
    y programa recordatorios.
    """
    log_section("PRUEBA: RECORDATORIO 24 HORAS (send_appointment_reminder)")
    
    from spa.tasks import send_appointment_reminder, _send_reminder_for_appointment
    
    user = get_or_create_test_user()
    service = get_or_create_test_service()
    
    now = timezone.now()
    # Crear cita para dentro de 24 horas y 30 minutos (dentro de la ventana 24h-25h)
    start_time = now + timedelta(hours=24, minutes=30)
    end_time = start_time + timedelta(hours=1)
    
    print(f"\n🕐 Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Creando cita para: {start_time.strftime('%Y-%m-%d %H:%M:%S')} (en ~24h)")
    
    # Crear nueva cita
    appointment = Appointment.objects.create(
        user=user,
        start_time=start_time,
        end_time=end_time,
        status=Appointment.AppointmentStatus.CONFIRMED,
        total=Decimal("75000"),
    )
    appointment.services.add(service)
    print(f"✅ Cita creada: {appointment.id}")
    
    # Contar notificaciones antes
    before_count = count_notifications_for_user(user, "APPOINTMENT_REMINDER_24H")
    
    # Opción A: Ejecutar la tarea completa (programa sub-tareas)
    print("\n⚙️ Ejecutando tarea: send_appointment_reminder()")
    result = send_appointment_reminder()
    print(f"   Resultado: {result}")
    
    # Opción B: Ejecutar directamente el recordatorio para esta cita
    print("\n⚙️ Ejecutando directamente: _send_reminder_for_appointment()")
    _send_reminder_for_appointment(str(appointment.id))
    
    print("   ⏳ Esperando 3s para que se procese...")
    time.sleep(3)
    
    # Verificar resultado
    success = show_notification_result(user, before_count, "APPOINTMENT_REMINDER_24H", result)
    
    return success


# =============================================================================
# PRUEBA 3: Cancelación automática por falta de pago
# =============================================================================
def test_trigger_cancel_unpaid():
    """
    Prueba: cancel_unpaid_appointments
    
    Cancela citas PENDING_PAYMENT que superaron el tiempo de expiración
    y envía notificación APPOINTMENT_CANCELLED_AUTO.
    """
    log_section("PRUEBA: CANCELACIÓN AUTOMÁTICA (cancel_unpaid_appointments)")
    
    from spa.tasks import cancel_unpaid_appointments
    
    user = get_or_create_test_user()
    service = get_or_create_test_service()
    
    # Obtener tiempo de expiración configurado
    settings_obj = GlobalSettings.load()
    expiration_minutes = settings_obj.advance_expiration_minutes
    print(f"\n⏱️ Tiempo de expiración configurado: {expiration_minutes} minutos")
    
    now = timezone.now()
    # Crear cita con created_at hace más del tiempo de expiración
    old_created_at = now - timedelta(minutes=expiration_minutes + 5)
    start_time = now + timedelta(hours=3)
    
    print(f"📅 Creando cita PENDING_PAYMENT creada hace {expiration_minutes + 5} min...")
    
    appointment = Appointment.objects.create(
        user=user,
        start_time=start_time,
        end_time=start_time + timedelta(hours=1),
        status=Appointment.AppointmentStatus.PENDING_PAYMENT,
        total=Decimal("75000"),
    )
    appointment.services.add(service)
    # Forzar created_at antiguo
    Appointment.objects.filter(id=appointment.id).update(created_at=old_created_at)
    appointment.refresh_from_db()
    
    print(f"✅ Cita creada: {appointment.id}")
    print(f"   Status: {appointment.status}")
    print(f"   Created at: {appointment.created_at}")
    
    # Contar notificaciones antes
    before_count = count_notifications_for_user(user, "APPOINTMENT_CANCELLED_AUTO")
    
    # Ejecutar la tarea
    print("\n⚙️ Ejecutando tarea: cancel_unpaid_appointments()")
    result = cancel_unpaid_appointments()
    
    print("   ⏳ Esperando 3s para que se procese...")
    time.sleep(3)
    
    # Verificar que la cita fue cancelada
    appointment.refresh_from_db()
    print(f"\n   📋 Status cita después: {appointment.status}")
    print(f"   📋 Outcome: {appointment.outcome}")
    
    # Verificar resultado
    success = show_notification_result(user, before_count, "APPOINTMENT_CANCELLED_AUTO", result)
    
    return success


# =============================================================================
# PRUEBA 4: VIP Membership Expired (downgrade)
# =============================================================================
def test_trigger_vip_expired():
    """
    Prueba: downgrade_expired_vips
    
    Degrada usuarios VIP cuyo periodo expiró y envía notificación.
    """
    log_section("PRUEBA: VIP EXPIRADO (downgrade_expired_vips)")
    
    from finances.tasks import downgrade_expired_vips
    
    user = get_or_create_test_user()
    
    # Configurar usuario como VIP expirado
    yesterday = timezone.now().date() - timedelta(days=1)
    user.role = CustomUser.Role.VIP
    user.vip_expires_at = yesterday
    user.vip_active_since = timezone.now().date() - timedelta(days=35)
    user.save()
    
    print(f"\n👤 Usuario configurado como VIP expirado:")
    print(f"   Role: {user.role}")
    print(f"   VIP expires at: {user.vip_expires_at}")
    
    # Contar notificaciones antes
    before_count = count_notifications_for_user(user, "VIP_MEMBERSHIP_EXPIRED")
    
    # Ejecutar la tarea
    print("\n⚙️ Ejecutando tarea: downgrade_expired_vips()")
    result = downgrade_expired_vips()
    
    print("   ⏳ Esperando 3s para que se procese...")
    time.sleep(3)
    
    # Verificar que el usuario fue degradado
    user.refresh_from_db()
    print(f"\n   📋 Role después: {user.role}")
    
    # Verificar resultado
    success = show_notification_result(user, before_count, "VIP_MEMBERSHIP_EXPIRED", result)
    
    return success


# =============================================================================
# MENÚ PRINCIPAL
# =============================================================================
def interactive_menu():
    """Menú interactivo para seleccionar pruebas"""
    tests = [
        ("Recordatorio 2 horas (APPOINTMENT_REMINDER_2H)", test_trigger_appointment_reminder_2h),
        ("Recordatorio 24 horas (APPOINTMENT_REMINDER_24H)", test_trigger_appointment_reminder_24h),
        ("Cancelación automática (APPOINTMENT_CANCELLED_AUTO)", test_trigger_cancel_unpaid),
        ("VIP Expirado (VIP_MEMBERSHIP_EXPIRED)", test_trigger_vip_expired),
    ]
    
    while True:
        log_section("PRUEBAS DE DISPARADORES DE NOTIFICACIONES")
        print(f"\n📱 Número destino: {TEST_PHONE}")
        print(f"🕐 Hora actual: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\nSelecciona qué probar:\n")
        
        for i, (name, _) in enumerate(tests, 1):
            print(f"  {i}. {name}")
        
        print(f"\n  A. Ejecutar TODAS las pruebas")
        print(f"  L. Ver logs de notificaciones recientes")
        print(f"  0. Salir")
        
        choice = input("\n> ").strip().upper()
        
        if choice == "0":
            print("\n👋 ¡Hasta luego!")
            break
        elif choice == "L":
            show_recent_logs()
        elif choice == "A":
            print("\n🚀 Ejecutando todas las pruebas...")
            results = []
            for name, test_func in tests:
                try:
                    success = test_func()
                    results.append((name, success))
                except Exception as e:
                    print(f"❌ Error en {name}: {e}")
                    results.append((name, False))
                time.sleep(5)  # Pausa entre pruebas
            
            log_section("RESUMEN DE RESULTADOS")
            for name, success in results:
                emoji = "✅" if success else "❌"
                print(f"  {emoji} {name}")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tests):
                    name, test_func = tests[idx]
                    try:
                        test_func()
                    except Exception as e:
                        print(f"❌ Error: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("❌ Opción inválida")
            except ValueError:
                print("❌ Opción inválida")
        
        input("\nPresiona Enter para continuar...")


def show_recent_logs():
    """Muestra logs recientes del usuario de prueba"""
    log_section("LOGS DE NOTIFICACIONES RECIENTES")
    
    user = CustomUser.objects.filter(phone_number=TEST_PHONE).first()
    if not user:
        print("⚠️ No existe usuario de prueba aún")
        return
    
    logs = NotificationLog.objects.filter(user=user).order_by('-created_at')[:10]
    
    if not logs:
        print("📭 No hay logs de notificaciones para este usuario")
        return
    
    for log in logs:
        status_emoji = {
            NotificationLog.Status.QUEUED: "🔄",
            NotificationLog.Status.SENT: "✅",
            NotificationLog.Status.FAILED: "❌",
            NotificationLog.Status.SILENCED: "🔇",
        }.get(log.status, "❓")
        
        print(f"\n{status_emoji} {log.event_code}")
        print(f"   Created: {log.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Status: {log.status}")
        print(f"   Canal: {log.channel}")
        if log.sent_at:
            print(f"   Enviado: {log.sent_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if log.error_message:
            print(f"   ⚠️ Error: {log.error_message}")


def main():
    log_section("PRUEBA DE DISPARADORES DE NOTIFICACIONES - STUDIOZENS")
    print(f"\n📱 Número destino: {TEST_PHONE}")
    print(f"🕐 Hora actual: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Verificar credenciales Twilio
    from django.conf import settings
    if not all([
        getattr(settings, 'TWILIO_ACCOUNT_SID', None),
        getattr(settings, 'TWILIO_AUTH_TOKEN', None),
        getattr(settings, 'TWILIO_WHATSAPP_FROM', None)
    ]):
        print("\n❌ ERROR: Credenciales de Twilio no configuradas")
        return
    
    print(f"✅ Credenciales Twilio OK")
    
    # Modo automático o interactivo
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "2h":
            test_trigger_appointment_reminder_2h()
        elif test_name == "24h":
            test_trigger_appointment_reminder_24h()
        elif test_name == "cancel":
            test_trigger_cancel_unpaid()
        elif test_name == "vip":
            test_trigger_vip_expired()
        elif test_name == "all":
            test_trigger_appointment_reminder_2h()
            time.sleep(10)
            test_trigger_appointment_reminder_24h()
            time.sleep(10)
            test_trigger_cancel_unpaid()
            time.sleep(10)
            test_trigger_vip_expired()
        else:
            print(f"Uso: python {sys.argv[0]} [2h|24h|cancel|vip|all]")
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
