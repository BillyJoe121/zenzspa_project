"""
Query Builder - Base de querysets.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Subquery, OuterRef, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from users.models import CustomUser
from spa.models import Appointment, Service
from finances.models import Payment
from marketplace.models import Order

from analytics.query_builder.schema import ENTITIES_BY_KEY

logger = logging.getLogger(__name__)


class QueryBuilderBase:
    """Configura entidad, modelo y queryset base."""

    # Mapeo de entidades a modelos Django
    MODEL_MAP = {
        "clients": CustomUser,
        "appointments": Appointment,
        "payments": Payment,
        "orders": Order,
        "services": Service,
    }

    # Campos de texto para búsqueda
    SEARCH_FIELDS = {
        "clients": ["first_name", "last_name", "email", "phone_number"],
        "appointments": ["user__first_name", "user__last_name", "user__phone_number"],
        "payments": ["user__first_name", "user__last_name", "user__phone_number"],
        "orders": ["user__first_name", "user__last_name", "user__phone_number"],
        "services": ["name", "description"],
    }

    def __init__(
        self,
        entity_key: str,
        filters: list[dict],
        ordering: str | None = None,
        limit: int = 100,
        aggregation: str | None = None,
        group_by: str | None = None,
    ):
        self.entity_key = entity_key
        self.filters = filters
        self.ordering = ordering
        self.limit = min(limit, 1000)  # Máximo 1000 registros
        self.aggregation = aggregation
        self.group_by = group_by

        if entity_key not in self.MODEL_MAP:
            raise ValueError(f"Entidad no válida: {entity_key}")

        self.model = self.MODEL_MAP[entity_key]
        self.entity_schema = ENTITIES_BY_KEY.get(entity_key)

    def _build_queryset(self):
        """Construye el queryset base con anotaciones necesarias."""
        queryset = self.model.objects.all()

        # Anotaciones específicas por entidad
        if self.entity_key == "clients":
            queryset = self._annotate_clients(queryset)
        elif self.entity_key == "appointments":
            queryset = queryset.select_related("user", "staff_member")
        elif self.entity_key == "payments":
            queryset = queryset.select_related("user")
        elif self.entity_key == "orders":
            queryset = queryset.select_related("user")
        elif self.entity_key == "services":
            queryset = queryset.select_related("category")

        # Filtrar solo clientes para la entidad clients
        if self.entity_key == "clients":
            queryset = queryset.filter(role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP])

        return queryset

    def _annotate_clients(self, queryset):
        """Agrega anotaciones computadas para clientes."""
        now = timezone.now()

        # Subquery para última cita
        last_appointment = Appointment.objects.filter(
            user=OuterRef("pk"),
            status=Appointment.AppointmentStatus.COMPLETED
        ).order_by("-start_time").values("start_time")[:1]

        # Subquery para total de citas
        total_appointments = Appointment.objects.filter(
            user=OuterRef("pk")
        ).values("user").annotate(count=Count("id")).values("count")

        # Subquery para citas completadas
        completed_appointments = Appointment.objects.filter(
            user=OuterRef("pk"),
            status=Appointment.AppointmentStatus.COMPLETED
        ).values("user").annotate(count=Count("id")).values("count")

        # Subquery para total gastado (pagos aprobados)
        total_spent = Payment.objects.filter(
            user=OuterRef("pk"),
            status=Payment.PaymentStatus.APPROVED
        ).values("user").annotate(total=Sum("amount")).values("total")

        return queryset.annotate(
            last_appointment_date=Subquery(last_appointment),
            total_appointments=Coalesce(Subquery(total_appointments), Value(0)),
            completed_appointments=Coalesce(Subquery(completed_appointments), Value(0)),
            total_spent=Coalesce(Subquery(total_spent), Value(Decimal("0"))),
        )
