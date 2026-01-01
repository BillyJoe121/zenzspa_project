"""
Management command para corregir estados de citas totalmente pagadas.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from spa.models import Appointment
from finances.payments import PaymentService


class Command(BaseCommand):
    help = 'Corrige citas en CONFIRMED/RESCHEDULED que deberían estar en FULLY_PAID'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra qué se cambiaría sin modificar nada',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("CORRECCIÓN DE ESTADOS DE CITAS TOTALMENTE PAGADAS"))
        self.stdout.write("=" * 70)
        self.stdout.write("")

        # Buscar citas en CONFIRMED o RESCHEDULED
        appointments = Appointment.objects.filter(
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.RESCHEDULED
            ]
        )

        total_count = appointments.count()
        self.stdout.write(f"Total de citas en CONFIRMED/RESCHEDULED: {total_count}")
        self.stdout.write("")

        to_update = []

        for apt in appointments:
            outstanding = PaymentService.calculate_outstanding_amount(apt)

            if outstanding <= Decimal('0'):
                to_update.append(apt)

                self.stdout.write(f"Cita {apt.id}")
                self.stdout.write(f"  Estado actual: {apt.get_status_display()}")
                self.stdout.write(f"  Precio: ${apt.price_at_purchase}")
                self.stdout.write(f"  Outstanding: ${outstanding}")
                self.stdout.write(self.style.SUCCESS(f"  -> Deberia estar en FULLY_PAID"))
                self.stdout.write("")

        self.stdout.write("=" * 70)
        self.stdout.write(f"RESUMEN: {len(to_update)} citas necesitan corrección")
        self.stdout.write("=" * 70)
        self.stdout.write("")

        if not to_update:
            self.stdout.write(self.style.SUCCESS("No se encontraron citas que necesiten corrección."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("MODO DRY-RUN: No se realizaron cambios"))
            self.stdout.write("Para aplicar los cambios, ejecuta sin --dry-run:")
            self.stdout.write("  python manage.py fix_fully_paid_status")
        else:
            updated = 0
            for apt in to_update:
                apt.status = Appointment.AppointmentStatus.FULLY_PAID
                apt.save(update_fields=['status', 'updated_at'])
                updated += 1

            self.stdout.write(self.style.SUCCESS(f"\n{updated} citas actualizadas exitosamente a FULLY_PAID"))
