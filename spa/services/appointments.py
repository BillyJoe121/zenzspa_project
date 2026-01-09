"""
Fachada para servicios de citas.

Reexporta AvailabilityService y AppointmentService desde módulos separados
para mantener compatibilidad con importaciones existentes.
"""

from .appointment_booking import AppointmentService
from .availability import AvailabilityService

__all__ = ["AvailabilityService", "AppointmentService"]
