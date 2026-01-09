import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from finances.payments import PaymentService
from users.models import CustomUser
from ..models import Appointment
from .availability import AvailabilityService

logger = logging.getLogger(__name__)


class AppointmentRescheduleMixin:
    @staticmethod
    @transaction.atomic
    def reschedule_appointment(appointment, new_start_time, acting_user, skip_counter=False):
        if not isinstance(new_start_time, datetime):
            raise ValidationError("La fecha y hora nuevas no son válidas.")

        is_privileged = acting_user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        now = timezone.now()
        restrictions = []

        if appointment.start_time - now <= timedelta(hours=24):
            restrictions.append("window")
        if appointment.reschedule_count >= 2:
            restrictions.append("limit")

        if restrictions and not is_privileged:
            raise ValidationError("Solo puedes reagendar hasta dos veces y con más de 24 horas de anticipación.")
        if restrictions and is_privileged:
            logger.info(
                "Staff %s bypassed reschedule restrictions (%s) for appointment %s",
                acting_user.id,
                ",".join(restrictions),
                appointment.id,
            )
            AuditLog.objects.create(
                admin_user=acting_user,
                target_user=appointment.user,
                target_appointment=appointment,
                action=AuditLog.Action.APPOINTMENT_RESCHEDULE_FORCE,
                details="Reagendamiento forzado por Staff fuera de ventana de política.",
            )

        if not is_privileged and appointment.user != acting_user:
            raise ValidationError("No puedes modificar citas de otros usuarios.")

        if new_start_time <= now:
            raise ValidationError("La nueva fecha debe estar en el futuro.")

        duration = timedelta(minutes=appointment.total_duration_minutes)
        new_end_time = new_start_time + duration
        buffer = AvailabilityService._buffer_delta()

        if appointment.staff_member:
            conflict = (
                Appointment.objects.select_for_update()
                .filter(
                    staff_member=appointment.staff_member,
                    status__in=[
                        Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT,
                        Appointment.AppointmentStatus.RESCHEDULED,
                        Appointment.AppointmentStatus.FULLY_PAID,
                    ],
                )
                .exclude(id=appointment.id)
                .filter(
                    start_time__lt=new_end_time + buffer,
                    end_time__gt=new_start_time - buffer,
                )
                .exists()
            )
            if conflict:
                raise ValidationError("El nuevo horario ya no está disponible.")

        appointment.start_time = new_start_time
        appointment.end_time = new_end_time

        should_increment = not (skip_counter and is_privileged)
        if should_increment:
            appointment.reschedule_count = appointment.reschedule_count + 1
        else:
            logger.info(
                "Staff %s reagendó cita %s sin incrementar contador (skip_counter=True)",
                acting_user.id,
                appointment.id,
            )
            AuditLog.objects.create(
                admin_user=acting_user,
                target_user=appointment.user,
                target_appointment=appointment,
                action=AuditLog.Action.APPOINTMENT_RESCHEDULE_FORCE,
                details="Reagendamiento por Staff sin afectar contador del cliente.",
            )

        appointment.status = Appointment.AppointmentStatus.RESCHEDULED
        appointment.save(update_fields=["start_time", "end_time", "reschedule_count", "status", "updated_at"])

        try:
            from notifications.services import NotificationService

            start_time_local = new_start_time.astimezone(timezone.get_current_timezone())

            NotificationService.send_notification(
                user=appointment.user,
                event_code="APPOINTMENT_RESCHEDULED",
                context={
                    "user_name": appointment.user.get_full_name() or appointment.user.first_name or "Cliente",
                    "new_date": start_time_local.strftime("%d de %B %Y"),
                    "new_time": start_time_local.strftime("%I:%M %p"),
                    "services": appointment.get_service_names(),
                },
                priority="high",
            )
            logger.info("Notificación de reagendamiento enviada para cita %s", appointment.id)
        except Exception as e:
            logger.exception("Error enviando notificación de reagendamiento para cita %s: %s", appointment.id, e)

        return appointment


class AppointmentCompletionMixin:
    @staticmethod
    @transaction.atomic
    def complete_appointment(appointment, acting_user):
        if acting_user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            raise ValidationError("No tienes permisos para completar esta cita.")
        outstanding = PaymentService.calculate_outstanding_amount(appointment)
        if outstanding > 0:
            raise ValidationError("No puedes completar la cita: existe un saldo final pendiente.")
        appointment.status = Appointment.AppointmentStatus.COMPLETED
        appointment.outcome = Appointment.AppointmentOutcome.NONE
        appointment.save(update_fields=["status", "outcome", "updated_at"])
        PaymentService.reset_user_cancellation_history(appointment)
        AuditLog.objects.create(
            admin_user=acting_user,
            target_user=appointment.user,
            target_appointment=appointment,
            action=AuditLog.Action.APPOINTMENT_COMPLETED,
            details=f"Cita {appointment.id} marcada como COMPLETED por {getattr(acting_user, 'phone_number', 'staff')}.",
        )
        return appointment


class AppointmentIcalMixin:
    @staticmethod
    def build_ical_event(appointment):
        dtstamp = timezone.now().astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dtstart = appointment.start_time.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dtend = appointment.end_time.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        summary = appointment.get_service_names() or "Cita StudioZens"
        description = f"Cita #{appointment.id}"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//StudioZens//Appointments//ES",
            "BEGIN:VEVENT",
            f"UID:{appointment.id}@studiozens",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{summary}",
            "LOCATION:StudioZens",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"
