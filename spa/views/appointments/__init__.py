"""
Módulo de vistas de appointments (citas).

Exporta todas las vistas y ViewSets para mantener compatibilidad con imports existentes.
"""
from .appointment_viewset import AppointmentViewSet
from .availability import AvailabilityCheckView
from .simple_viewsets import (
    PackageViewSet,
    ServiceCategoryViewSet,
    ServiceViewSet,
    StaffAvailabilityViewSet,
)

__all__ = [
    'AppointmentViewSet',
    'AvailabilityCheckView',
    'PackageViewSet',
    'ServiceCategoryViewSet',
    'ServiceViewSet',
    'StaffAvailabilityViewSet',
]
