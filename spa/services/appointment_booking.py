from .appointment_booking_actions import AppointmentCompletionMixin, AppointmentIcalMixin, AppointmentRescheduleMixin
from .appointment_booking_base import AppointmentServiceBase


class AppointmentService(
    AppointmentServiceBase,
    AppointmentRescheduleMixin,
    AppointmentCompletionMixin,
    AppointmentIcalMixin,
):
    """
    Servicio para manejar la lógica de negocio de la creación de citas.

    Mantiene compatibilidad con métodos públicos anteriores (reschedule, complete, build_ical).
    """
