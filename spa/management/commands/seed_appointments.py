"""
Seed command para crear citas realistas con pagos correctos.

Uso:
    python manage.py seed_appointments
    python manage.py seed_appointments --min-per-client=2 --max-per-client=5
"""
import random
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from users.models import CustomUser
from spa.models import (
    Appointment,
    AppointmentItem,
    Service,
    StaffAvailability,
)
from finances.models import Payment
from core.models import GlobalSettings


class Command(BaseCommand):
    help = 'Crea citas realistas con pagos correctos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-per-client',
            type=int,
            default=2,
            help='Mínimo de citas por cliente (default: 2)'
        )
        parser.add_argument(
            '--max-per-client',
            type=int,
            default=5,
            help='Máximo de citas por cliente (default: 5)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula sin crear datos reales'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Borra todas las citas existentes antes de crear nuevas'
        )

    def handle(self, *args, **options):
        self.min_per_client = options['min_per_client']
        self.max_per_client = options['max_per_client']
        self.dry_run = options['dry_run']
        
        if options['clear'] and not self.dry_run:
            self._clear_all()
        
        self.stdout.write(self.style.NOTICE('🌱 Iniciando seed de citas...'))
        
        # 1. Obtener clientes verificados y activos
        clients = list(CustomUser.objects.filter(
            role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
            is_active=True,
            is_verified=True,
            is_persona_non_grata=False
        ))
        
        if not clients:
            self.stdout.write(self.style.ERROR('❌ No hay clientes verificados y activos.'))
            return
        
        self.stdout.write(f'👤 Clientes: {len(clients)}')
        for c in clients:
            self.stdout.write(f'   - {c.first_name} ({c.role})')
        
        # 2. Obtener staff activo con disponibilidad
        staff_list = list(CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True,
            availabilities__isnull=False
        ).distinct())
        
        if not staff_list:
            self.stdout.write(self.style.ERROR('❌ No hay staff con horarios disponibles.'))
            return
        
        self.stdout.write(f'👨‍⚕️ Staff: {len(staff_list)}')
        
        # Cargar disponibilidades
        self.staff_availabilities = {}
        for staff in staff_list:
            self.staff_availabilities[staff.id] = list(
                StaffAvailability.objects.filter(staff_member=staff)
            )
        
        # 3. Obtener servicios activos
        services = list(Service.objects.filter(is_active=True))
        
        if not services:
            self.stdout.write(self.style.ERROR('❌ No hay servicios activos.'))
            return
        
        self.stdout.write(f'🛎️ Servicios: {len(services)}')
        
        # 4. Obtener configuración global
        global_settings = GlobalSettings.load()
        self.advance_percentage = Decimal(str(global_settings.advance_payment_percentage)) / Decimal('100')
        self.stdout.write(f'💰 Porcentaje anticipo: {global_settings.advance_payment_percentage}%')
        
        # 5. Definir rango de fechas
        today = timezone.now().date()
        start_date = today - timedelta(days=15)
        end_date = today + timedelta(days=45)
        
        self.stdout.write(f'📅 Fechas: {start_date} a {end_date}')
        
        # 6. Crear citas
        appointments_created = 0
        payments_advance = 0
        payments_full = 0
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('🧪 MODO DRY-RUN: No se crearán datos reales'))
            return
        
        for client in clients:
            num_appointments = random.randint(self.min_per_client, self.max_per_client)
            client_appointments = 0
            
            for attempt in range(num_appointments * 3):  # Más intentos por conflictos
                if client_appointments >= num_appointments:
                    break
                    
                result = self._create_appointment(
                    client=client,
                    staff_list=staff_list,
                    services_list=services,
                    start_date=start_date,
                    end_date=end_date,
                    today=today
                )
                
                if result:
                    appointment, payment_type = result
                    appointments_created += 1
                    client_appointments += 1
                    if payment_type == 'advance':
                        payments_advance += 1
                    else:
                        payments_full += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ Completado: {appointments_created} citas'
        ))
        self.stdout.write(f'   - Con anticipo (40%): {payments_advance}')
        self.stdout.write(f'   - Pago completo: {payments_full}')

    def _clear_all(self):
        from spa.models import AppointmentItem
        AppointmentItem.objects.all().delete()
        Payment.objects.filter(appointment__isnull=False).delete()
        Appointment.objects.all().delete()
        self.stdout.write(self.style.WARNING('🗑️ Citas anteriores eliminadas'))

    @transaction.atomic
    def _create_appointment(self, client, staff_list, services_list, start_date, end_date, today):
        """Crea una cita con pagos correctos."""
        
        # Seleccionar staff aleatorio
        staff = random.choice(staff_list)
        
        # Seleccionar 1-2 servicios aleatorios
        num_services = random.randint(1, min(2, len(services_list)))
        selected_services = random.sample(services_list, num_services)
        
        # Calcular duración total
        total_duration = sum(s.duration for s in selected_services)
        
        # Generar fecha aleatoria
        days_range = (end_date - start_date).days
        random_day_offset = random.randint(0, days_range)
        appointment_date = start_date + timedelta(days=random_day_offset)
        
        # Obtener disponibilidad del staff para ese día
        day_of_week = appointment_date.isoweekday()
        staff_availability = [
            a for a in self.staff_availabilities.get(staff.id, [])
            if a.day_of_week == day_of_week
        ]
        
        if not staff_availability:
            return None
        
        # Seleccionar bloque de disponibilidad aleatorio
        availability = random.choice(staff_availability)
        
        # Generar hora de inicio
        max_start_minutes = (availability.end_time.hour * 60 + availability.end_time.minute) - total_duration - 15
        min_start_minutes = availability.start_time.hour * 60 + availability.start_time.minute
        
        if max_start_minutes <= min_start_minutes:
            return None
        
        possible_starts = list(range(min_start_minutes, max_start_minutes, 15))
        if not possible_starts:
            return None
        
        start_minutes = random.choice(possible_starts)
        start_time_obj = time(start_minutes // 60, start_minutes % 60)
        
        tz = timezone.get_current_timezone()
        start_datetime = timezone.make_aware(
            datetime.combine(appointment_date, start_time_obj),
            timezone=tz
        )
        end_datetime = start_datetime + timedelta(minutes=total_duration)
        
        # Verificar conflictos
        conflict = Appointment.objects.filter(
            staff_member=staff,
            start_time__lt=end_datetime,
            end_time__gt=start_datetime,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.RESCHEDULED,
                Appointment.AppointmentStatus.PENDING_PAYMENT,
            ]
        ).exists()
        
        if conflict:
            return None
        
        # ========================================
        # CALCULAR PRECIOS CORRECTOS
        # ========================================
        is_vip = client.role == CustomUser.Role.VIP
        total_price = Decimal('0')
        service_prices = []
        
        for service in selected_services:
            if is_vip and service.vip_price:
                price = service.vip_price
            else:
                price = service.price
            total_price += price
            service_prices.append((service, price))
        
        # Calcular anticipo (40% del total)
        advance_amount = (total_price * self.advance_percentage).quantize(Decimal('1'))
        remaining_amount = total_price - advance_amount
        
        # ========================================
        # DECIDIR TIPO DE PAGO Y ESTADO
        # ========================================
        is_past = appointment_date < today
        pay_full = random.random() < 0.4  # 40% pagan completo
        
        if is_past:
            # Citas pasadas: COMPLETED, con todos los pagos hechos
            status = Appointment.AppointmentStatus.COMPLETED
        else:
            # Citas futuras: CONFIRMED
            status = Appointment.AppointmentStatus.CONFIRMED
        
        # ========================================
        # CREAR CITA
        # ========================================
        appointment = Appointment.objects.create(
            user=client,
            staff_member=staff,
            start_time=start_datetime,
            end_time=end_datetime,
            price_at_purchase=total_price,
            status=status,
            outcome=Appointment.AppointmentOutcome.NONE
        )
        
        # Crear items con precios correctos
        for service, price in service_prices:
            AppointmentItem.objects.create(
                appointment=appointment,
                service=service,
                duration=service.duration,
                price_at_purchase=price
            )
        
        # ========================================
        # CREAR PAGOS
        # ========================================
        if pay_full:
            # Pago completo (total)
            Payment.objects.create(
                user=client,
                appointment=appointment,
                amount=total_price,
                payment_type=Payment.PaymentType.FINAL,
                status=Payment.PaymentStatus.APPROVED,
                transaction_id=f"SEED-FULL-{uuid.uuid4().hex[:8]}"
            )
            payment_type = 'full'
        else:
            # Solo anticipo
            Payment.objects.create(
                user=client,
                appointment=appointment,
                amount=advance_amount,
                payment_type=Payment.PaymentType.ADVANCE,
                status=Payment.PaymentStatus.APPROVED,
                transaction_id=f"SEED-ADV-{uuid.uuid4().hex[:8]}"
            )
            
            # Si es cita pasada, también crear pago final
            if is_past and remaining_amount > 0:
                Payment.objects.create(
                    user=client,
                    appointment=appointment,
                    amount=remaining_amount,
                    payment_type=Payment.PaymentType.FINAL,
                    status=Payment.PaymentStatus.APPROVED,
                    transaction_id=f"SEED-FIN-{uuid.uuid4().hex[:8]}"
                )
            
            payment_type = 'advance'
        
        return appointment, payment_type
