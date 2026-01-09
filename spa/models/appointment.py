"""
Fachada para modelos de citas.

Reexporta las clases divididas en módulos específicos para mantener
compatibilidad con ``from spa.models.appointment import ...``.
"""

from .appointment_core import Appointment, AppointmentItem, AppointmentItemManager
from .availability import AvailabilityExclusion, StaffAvailability
from .services import Service, ServiceCategory, ServiceMedia
from .waitlist import WaitlistEntry

__all__ = [
    "Appointment",
    "AppointmentItem",
    "AppointmentItemManager",
    "AvailabilityExclusion",
    "Service",
    "ServiceCategory",
    "ServiceMedia",
    "StaffAvailability",
    "WaitlistEntry",
]
