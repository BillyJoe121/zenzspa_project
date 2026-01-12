from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction

from spa.models import StaffAvailability
from users.models import CustomUser


class Command(BaseCommand):
    help = "Crea horarios de disponibilidad para el staff del 14 al 20 de diciembre de 2025."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Elimina todos los horarios existentes antes de crear los nuevos',
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            # Obtener todos los miembros del staff
            staff_members = CustomUser.objects.filter(role__in=['STAFF', 'ADMIN'])

            if not staff_members.exists():
                self.stdout.write(self.style.WARNING("No se encontraron miembros del staff."))
                return

            # Si se especifica --clear, eliminar todos los horarios existentes
            if options['clear']:
                deleted_count = StaffAvailability.objects.all().delete()[0]
                self.stdout.write(self.style.WARNING(f"Eliminados {deleted_count} horarios existentes."))

            # Días de la semana del 14 al 20 de diciembre de 2025
            # 14 dic = Domingo (7), 15 = Lunes (1), ..., 20 = Sábado (6)
            days_of_week = [7, 1, 2, 3, 4, 5, 6]  # Domingo a Sábado

            # Horarios:
            # - 9:30 AM a 11:00 AM
            # - 3:00 PM a 4:00 PM
            availability_blocks = [
                {'start_time': time(9, 30), 'end_time': time(11, 0)},
                {'start_time': time(15, 0), 'end_time': time(16, 0)},
            ]

            created_count = 0
            updated_count = 0

            for staff in staff_members:
                for day_of_week in days_of_week:
                    for block in availability_blocks:
                        availability, created = StaffAvailability.objects.get_or_create(
                            staff_member=staff,
                            day_of_week=day_of_week,
                            start_time=block['start_time'],
                            end_time=block['end_time'],
                        )

                        if created:
                            created_count += 1
                        else:
                            updated_count += 1

        self.stdout.write(self.style.SUCCESS("Seed de horarios de disponibilidad completado."))
        self.stdout.write(f"Staff members procesados: {staff_members.count()}")
        self.stdout.write(f"Bloques de horario creados: {created_count}")
        self.stdout.write(f"Bloques ya existentes: {updated_count}")
        self.stdout.write("")
        self.stdout.write("Horarios configurados para cada staff member:")
        self.stdout.write("  Domingo a Sábado (14-20 dic 2025):")
        self.stdout.write("    - 9:30 AM a 11:00 AM")
        self.stdout.write("    - 3:00 PM a 4:00 PM")
