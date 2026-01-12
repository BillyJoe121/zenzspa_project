"""
Fachada para serializadores de citas.

Reexporta clases divididas en módulos más pequeños para mantener compatibilidad
con ``from spa.serializers.appointment import ...``.
"""

from .appointment_actions import (
    AppointmentCancelSerializer,
    AppointmentCreateSerializer,
    AppointmentStatusUpdateSerializer,
    TipCreateSerializer,
)
from .appointment_admin import AdminAppointmentCreateSerializer, ReceiveAdvanceInPersonSerializer
from .appointment_availability import (
    AppointmentRescheduleSerializer,
    AvailabilityCheckSerializer,
    StaffAvailabilitySerializer,
    WaitlistConfirmSerializer,
    WaitlistJoinSerializer,
)
from .appointment_common import CustomUser, ServiceSummarySerializer, UserSummarySerializer
from .appointment_read import AppointmentListSerializer, AppointmentReadSerializer, AppointmentSerializer
from .appointment_services import (
    AppointmentItemSerializer,
    ServiceCategorySerializer,
    ServiceMediaSerializer,
    ServiceSerializer,
)

__all__ = [
    "CustomUser",
    "UserSummarySerializer",
    "ServiceSummarySerializer",
    "ServiceCategorySerializer",
    "ServiceMediaSerializer",
    "ServiceSerializer",
    "AppointmentItemSerializer",
    "AppointmentListSerializer",
    "AppointmentReadSerializer",
    "AppointmentSerializer",
    "AppointmentCreateSerializer",
    "TipCreateSerializer",
    "AppointmentCancelSerializer",
    "AppointmentStatusUpdateSerializer",
    "StaffAvailabilitySerializer",
    "AvailabilityCheckSerializer",
    "AppointmentRescheduleSerializer",
    "WaitlistJoinSerializer",
    "WaitlistConfirmSerializer",
    "AdminAppointmentCreateSerializer",
    "ReceiveAdvanceInPersonSerializer",
]
