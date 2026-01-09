"""
Query Builder - Filtrado.
"""
import logging
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from users.models import CustomUser

from analytics.query_builder.types import Operator

logger = logging.getLogger(__name__)


class QueryBuilderFilteringMixin:
    """Aplica filtros declarativos y computados sobre el queryset."""

    def _apply_filter(self, queryset, filter_config: dict):
        """Aplica un filtro individual al queryset."""
        field_key = filter_config.get("field")
        operator = filter_config.get("operator")
        value = filter_config.get("value")
        value2 = filter_config.get("value2")  # Para operador BETWEEN

        if not field_key or not operator:
            return queryset

        # Obtener la definición del campo
        field_def = self._get_field_definition(field_key)
        if not field_def:
            logger.warning("Campo no encontrado: %s", field_key)
            return queryset

        db_field = field_def.db_field

        # Manejar campos computados especiales
        if db_field.startswith("__"):
            return self._apply_computed_filter(queryset, db_field, operator, value, value2)

        # Construir el filtro Q
        q_filter = self._build_q_filter(db_field, operator, value, value2)
        if q_filter:
            queryset = queryset.filter(q_filter)

        return queryset

    def _get_field_definition(self, field_key: str):
        """Obtiene la definición de un campo del schema."""
        if not self.entity_schema:
            return None
        for field_def in self.entity_schema.filters:
            if field_def.key == field_key:
                return field_def
        return None

    def _build_q_filter(self, db_field: str, operator: str, value: Any, value2: Any = None) -> Q:
        """Construye un objeto Q para Django ORM."""
        if operator == Operator.EQUALS.value:
            return Q(**{db_field: value})

        elif operator == Operator.NOT_EQUALS.value:
            return ~Q(**{db_field: value})

        elif operator == Operator.CONTAINS.value:
            return Q(**{f"{db_field}__icontains": value})

        elif operator == Operator.GREATER_THAN.value:
            return Q(**{f"{db_field}__gt": value})

        elif operator == Operator.LESS_THAN.value:
            return Q(**{f"{db_field}__lt": value})

        elif operator == Operator.GREATER_OR_EQUAL.value:
            return Q(**{f"{db_field}__gte": value})

        elif operator == Operator.LESS_OR_EQUAL.value:
            return Q(**{f"{db_field}__lte": value})

        elif operator == Operator.BETWEEN.value:
            return Q(**{f"{db_field}__gte": value, f"{db_field}__lte": value2})

        elif operator == Operator.IN.value:
            values = value if isinstance(value, list) else [value]
            return Q(**{f"{db_field}__in": values})

        elif operator == Operator.NOT_IN.value:
            values = value if isinstance(value, list) else [value]
            return ~Q(**{f"{db_field}__in": values})

        elif operator == Operator.IS_NULL.value:
            return Q(**{f"{db_field}__isnull": True})

        elif operator == Operator.IS_NOT_NULL.value:
            return Q(**{f"{db_field}__isnull": False})

        elif operator == Operator.DAYS_AGO_MORE_THAN.value:
            cutoff = timezone.now() - timedelta(days=int(value))
            return Q(**{f"{db_field}__lt": cutoff})

        elif operator == Operator.DAYS_AGO_LESS_THAN.value:
            cutoff = timezone.now() - timedelta(days=int(value))
            return Q(**{f"{db_field}__gte": cutoff})

        return None

    def _apply_computed_filter(self, queryset, computed_field: str,
                               operator: str, value: Any, value2: Any = None):
        """Aplica filtros a campos computados."""

        # Búsqueda de texto
        if computed_field == "__search" or computed_field == "__client_search":
            if value:
                search_fields = self.SEARCH_FIELDS.get(self.entity_key, [])
                q_search = Q()
                for field in search_fields:
                    q_search |= Q(**{f"{field}__icontains": value})
                queryset = queryset.filter(q_search)
            return queryset

        # Es VIP activo
        if computed_field == "__computed_is_vip":
            if value is True:
                now = timezone.now()
                queryset = queryset.filter(
                    role=CustomUser.Role.VIP,
                    vip_expires_at__gt=now
                )
            elif value is False:
                now = timezone.now()
                queryset = queryset.exclude(
                    role=CustomUser.Role.VIP,
                    vip_expires_at__gt=now
                )
            return queryset

        # Tiene email
        if computed_field == "__computed_has_email":
            if value is True:
                queryset = queryset.exclude(email__isnull=True).exclude(email="")
            elif value is False:
                queryset = queryset.filter(Q(email__isnull=True) | Q(email=""))
            return queryset

        # Campos anotados (last_appointment_date, total_appointments, etc.)
        annotated_field = computed_field.replace("__computed_", "")
        q_filter = self._build_q_filter(annotated_field, operator, value, value2)
        if q_filter:
            queryset = queryset.filter(q_filter)

        return queryset
