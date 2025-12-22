"""
Query Builder Service - Ejecuta queries dinámicas de forma segura.

Este servicio toma la configuración del Query Builder y la convierte
en queries Django ORM, evitando SQL injection.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import (
    Q, Count, Sum, Avg, Min, Max, F, Value,
    CharField, DecimalField, IntegerField, DateField,
    Subquery, OuterRef, Exists
)
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth, TruncYear
from django.utils import timezone

from users.models import CustomUser
from spa.models import Appointment, Service, ServiceCategory
from finances.models import Payment
from marketplace.models import Order

from .query_builder_schema import (
    ENTITIES_BY_KEY, 
    Operator, 
    FieldType,
    EntitySchema,
)

logger = logging.getLogger(__name__)


class QueryBuilderService:
    """Servicio para ejecutar queries dinámicas del Query Builder."""
    
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
    
    def __init__(self, entity_key: str, filters: list[dict], 
                 ordering: str = None, limit: int = 100,
                 aggregation: str = None, group_by: str = None):
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
    
    def execute(self) -> dict:
        """Ejecuta la query y retorna los resultados."""
        try:
            queryset = self._build_queryset()
            
            # Aplicar filtros
            for filter_config in self.filters:
                queryset = self._apply_filter(queryset, filter_config)
            
            # Si hay agregación con group_by
            if self.aggregation and self.group_by:
                return self._execute_grouped_aggregation(queryset)
            
            # Si hay agregación simple
            if self.aggregation:
                return self._execute_simple_aggregation(queryset)
            
            # Query normal con resultados
            return self._execute_list_query(queryset)
            
        except Exception as e:
            logger.error("Error en Query Builder: %s", str(e), exc_info=True)
            raise ValueError(f"Error al ejecutar la consulta: {str(e)}")
    
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
    
    def _execute_list_query(self, queryset) -> dict:
        """Ejecuta query de lista con resultados."""
        # Ordenamiento
        ordering = self.ordering or self.entity_schema.default_ordering
        if ordering:
            queryset = queryset.order_by(ordering)
        
        # Límite
        queryset = queryset[:self.limit]
        
        # Serializar resultados
        results = self._serialize_results(list(queryset))
        
        return {
            "type": "list",
            "count": len(results),
            "results": results,
        }
    
    def _execute_simple_aggregation(self, queryset) -> dict:
        """Ejecuta una agregación simple."""
        agg_func = self._get_aggregation_function()
        
        if self.aggregation == "count":
            result = queryset.count()
        else:
            # Para otras agregaciones, necesitamos un campo
            result = queryset.aggregate(value=agg_func)
            result = result.get("value")
        
        return {
            "type": "aggregation",
            "aggregation": self.aggregation,
            "value": result,
        }
    
    def _execute_grouped_aggregation(self, queryset) -> dict:
        """Ejecuta una agregación agrupada."""
        trunc_func = self._get_trunc_function()
        agg_func = self._get_aggregation_function()
        
        # Determinar el campo de fecha para agrupar
        date_field = self._get_date_field_for_grouping()
        
        if not date_field:
            raise ValueError("No se encontró un campo de fecha para agrupar")
        
        queryset = queryset.annotate(
            period=trunc_func(date_field)
        ).values("period").annotate(
            value=agg_func if self.aggregation != "count" else Count("id")
        ).order_by("period")
        
        return {
            "type": "grouped_aggregation",
            "aggregation": self.aggregation,
            "groupBy": self.group_by,
            "results": list(queryset),
        }
    
    def _get_aggregation_function(self):
        """Retorna la función de agregación Django."""
        if self.aggregation == "count":
            return Count("id")
        elif self.aggregation == "sum":
            return Sum(self._get_numeric_field())
        elif self.aggregation == "avg":
            return Avg(self._get_numeric_field())
        elif self.aggregation == "min":
            return Min(self._get_numeric_field())
        elif self.aggregation == "max":
            return Max(self._get_numeric_field())
        return Count("id")
    
    def _get_trunc_function(self):
        """Retorna la función de truncamiento de fecha."""
        if self.group_by == "day":
            return TruncDay
        elif self.group_by == "week":
            return TruncWeek
        elif self.group_by == "month":
            return TruncMonth
        elif self.group_by == "year":
            return TruncYear
        return TruncMonth
    
    def _get_numeric_field(self) -> str:
        """Retorna el campo numérico principal de la entidad."""
        numeric_fields = {
            "clients": "total_spent",
            "appointments": "price_at_purchase",
            "payments": "amount",
            "orders": "total_amount",
            "services": "price",
        }
        return numeric_fields.get(self.entity_key, "id")
    
    def _get_date_field_for_grouping(self) -> str:
        """Retorna el campo de fecha para agrupar."""
        date_fields = {
            "clients": "created_at",
            "appointments": "start_time",
            "payments": "created_at",
            "orders": "created_at",
            "services": "created_at",
        }
        return date_fields.get(self.entity_key)
    
    def _serialize_results(self, objects: list) -> list[dict]:
        """Serializa los resultados según la entidad."""
        serializer = getattr(self, f"_serialize_{self.entity_key}", self._serialize_generic)
        return [serializer(obj) for obj in objects]
    
    def _serialize_clients(self, obj: CustomUser) -> dict:
        """Serializa un cliente."""
        return {
            "id": str(obj.id),
            "phone_number": obj.phone_number,
            "email": obj.email or "",
            "first_name": obj.first_name or "",
            "last_name": obj.last_name or "",
            "full_name": obj.get_full_name(),
            "role": obj.role,
            "is_vip": obj.is_vip,
            "vip_expires_at": obj.vip_expires_at.isoformat() if obj.vip_expires_at else None,
            "date_joined": obj.created_at.isoformat() if obj.created_at else None,
            "is_persona_non_grata": obj.is_persona_non_grata,
            "last_appointment_date": getattr(obj, "last_appointment_date", None),
            "total_appointments": getattr(obj, "total_appointments", 0),
            "completed_appointments": getattr(obj, "completed_appointments", 0),
            "total_spent": float(getattr(obj, "total_spent", 0) or 0),
        }
    
    def _serialize_appointments(self, obj: Appointment) -> dict:
        """Serializa una cita."""
        return {
            "id": str(obj.id),
            "date": obj.start_time.isoformat() if obj.start_time else None,
            "start_time": obj.start_time.isoformat() if obj.start_time else None,
            "status": obj.status,
            "outcome": obj.outcome,
            "total_amount": float(obj.price_at_purchase or 0),
            "client": {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name(),
                "phone": obj.user.phone_number,
            } if obj.user else None,
            "staff": {
                "id": str(obj.staff_member.id),
                "name": obj.staff_member.get_full_name(),
            } if obj.staff_member else None,
            "reschedule_count": obj.reschedule_count,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
        }
    
    def _serialize_payments(self, obj: Payment) -> dict:
        """Serializa un pago."""
        return {
            "id": str(obj.id),
            "amount": float(obj.amount or 0),
            "status": obj.status,
            "payment_type": obj.payment_type,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "client": {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name(),
                "phone": obj.user.phone_number,
            } if obj.user else None,
            "wompi_reference": obj.wompi_reference or "",
        }
    
    def _serialize_orders(self, obj: Order) -> dict:
        """Serializa una orden."""
        return {
            "id": str(obj.id),
            "status": obj.status,
            "total_amount": float(obj.total_amount or 0),
            "shipping_cost": float(obj.shipping_cost or 0),
            "delivery_option": obj.delivery_option,
            "delivery_address": obj.delivery_address or "",
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "client": {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name(),
                "phone": obj.user.phone_number,
            } if obj.user else None,
        }
    
    def _serialize_services(self, obj: Service) -> dict:
        """Serializa un servicio."""
        return {
            "id": str(obj.id),
            "name": obj.name,
            "description": obj.description[:200] if obj.description else "",
            "price": float(obj.price or 0),
            "vip_price": float(obj.vip_price or 0) if obj.vip_price else None,
            "duration": obj.duration,
            "is_active": obj.is_active,
            "category": obj.category.name if obj.category else None,
        }
    
    def _serialize_generic(self, obj) -> dict:
        """Serialización genérica para cualquier modelo."""
        return {
            "id": str(obj.id) if hasattr(obj, "id") else None,
            "created_at": obj.created_at.isoformat() if hasattr(obj, "created_at") and obj.created_at else None,
        }
