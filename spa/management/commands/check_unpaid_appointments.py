"""
Management command para revisar citas pendientes de pago.
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import GlobalSettings
from spa.models import Appointment


class Command(BaseCommand):
    help = 'Muestra información sobre citas pendientes de pago'

    def handle(self, *args, **options):
        settings_obj = GlobalSettings.load()
        expiration_minutes = settings_obj.advance_expiration_minutes

        self.stdout.write(f'⏱️  Tiempo de expiración configurado: {expiration_minutes} minutos')

        # Todas las citas PENDING_PAYMENT
        all_pending = Appointment.objects.filter(
            status=Appointment.AppointmentStatus.PENDING_PAYMENT
        ).order_by('created_at')

        self.stdout.write(f'\n📋 Total de citas PENDING_PAYMENT: {all_pending.count()}')

        if not all_pending.exists():
            self.stdout.write(self.style.SUCCESS('✅ No hay citas pendientes de pago'))
            return

        # Citas que deberían cancelarse
        time_threshold = timezone.now() - timedelta(minutes=expiration_minutes)
        expired = all_pending.filter(created_at__lt=time_threshold)

        self.stdout.write(f'❌ Citas que deberían estar canceladas: {expired.count()}')

        if expired.exists():
            self.stdout.write('\n--- Citas Expiradas ---')
            for appt in expired:
                age_minutes = (timezone.now() - appt.created_at).total_seconds() / 60
                self.stdout.write(
                    f'  • ID: {appt.id} | Usuario: {appt.user.email} | '
                    f'Creada hace: {age_minutes:.0f} min | '
                    f'Fecha cita: {appt.start_time.strftime("%Y-%m-%d %H:%M")}'
                )

        # Citas aún vigentes
        not_expired = all_pending.filter(created_at__gte=time_threshold)
        self.stdout.write(f'\n⏳ Citas aún vigentes (dentro del tiempo): {not_expired.count()}')

        if not_expired.exists():
            self.stdout.write('\n--- Citas Vigentes ---')
            for appt in not_expired:
                remaining_minutes = expiration_minutes - ((timezone.now() - appt.created_at).total_seconds() / 60)
                self.stdout.write(
                    f'  • ID: {appt.id} | Usuario: {appt.user.email} | '
                    f'Tiempo restante: {remaining_minutes:.0f} min | '
                    f'Fecha cita: {appt.start_time.strftime("%Y-%m-%d %H:%M")}'
                )

        if expired.exists():
            self.stdout.write('\n' + self.style.WARNING(
                f'⚠️  ACCIÓN REQUERIDA: Ejecuta "python manage.py cancel_unpaid_appointments" '
                f'para cancelar las {expired.count()} citas expiradas'
            ))
