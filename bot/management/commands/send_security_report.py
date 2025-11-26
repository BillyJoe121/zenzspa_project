"""
Comando Django para enviar el reporte diario de seguridad.
Uso: python manage.py send_security_report

Este comando puede ser ejecutado manualmente o programado con cron/celery.
"""
from django.core.management.base import BaseCommand
from bot.alerts import SuspiciousActivityAlertService


class Command(BaseCommand):
    help = 'Envía el reporte diario de seguridad a los administradores'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Enviando reporte diario de seguridad...'))

        try:
            SuspiciousActivityAlertService.send_daily_security_report()
            self.stdout.write(self.style.SUCCESS('✅ Reporte enviado exitosamente'))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error enviando reporte: {e}')
            )
            raise
