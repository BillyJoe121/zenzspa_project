"""
Management command para cancelar citas con pago pendiente.
Útil para ejecutar manualmente la tarea sin Celery.
"""
from django.core.management.base import BaseCommand
from spa.tasks import cancel_unpaid_appointments


class Command(BaseCommand):
    help = 'Cancela citas cuyo anticipo no se ha pagado dentro del tiempo límite'

    def handle(self, *args, **options):
        self.stdout.write('Ejecutando cancelación de citas sin pago...')
        result = cancel_unpaid_appointments()
        self.stdout.write(self.style.SUCCESS(result))
