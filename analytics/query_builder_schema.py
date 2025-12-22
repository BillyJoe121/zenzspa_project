"""
Query Builder Schema para el panel administrativo.

Define las entidades, filtros y operadores disponibles para que el frontend
pueda renderizar dinámicamente un constructor de queries.
"""
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class FieldType(str, Enum):
    """Tipos de campo para filtros."""
    TEXT = "text"
    NUMBER = "number"
    MONEY = "money"
    DATE = "date"
    DATE_RANGE = "date_range"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTI_SELECT = "multi_select"


class Operator(str, Enum):
    """Operadores disponibles para filtros."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_OR_EQUAL = "less_or_equal"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    DAYS_AGO_MORE_THAN = "days_ago_more_than"
    DAYS_AGO_LESS_THAN = "days_ago_less_than"


# Operadores por tipo de campo
OPERATORS_BY_TYPE = {
    FieldType.TEXT: [Operator.EQUALS, Operator.NOT_EQUALS, Operator.CONTAINS],
    FieldType.NUMBER: [
        Operator.EQUALS, Operator.NOT_EQUALS, 
        Operator.GREATER_THAN, Operator.LESS_THAN,
        Operator.GREATER_OR_EQUAL, Operator.LESS_OR_EQUAL,
        Operator.BETWEEN
    ],
    FieldType.MONEY: [
        Operator.EQUALS, Operator.GREATER_THAN, Operator.LESS_THAN,
        Operator.GREATER_OR_EQUAL, Operator.LESS_OR_EQUAL, Operator.BETWEEN
    ],
    FieldType.DATE: [
        Operator.EQUALS, Operator.GREATER_THAN, Operator.LESS_THAN,
        Operator.BETWEEN, Operator.DAYS_AGO_MORE_THAN, Operator.DAYS_AGO_LESS_THAN,
        Operator.IS_NULL, Operator.IS_NOT_NULL
    ],
    FieldType.DATE_RANGE: [Operator.BETWEEN],
    FieldType.BOOLEAN: [Operator.EQUALS],
    FieldType.SELECT: [Operator.EQUALS, Operator.NOT_EQUALS, Operator.IN, Operator.NOT_IN],
    FieldType.MULTI_SELECT: [Operator.IN, Operator.NOT_IN],
}


# Operadores con metadatos completos
OPERATOR_DEFINITIONS = {
    Operator.EQUALS: {"label": "es igual a", "requiresValue": True},
    Operator.NOT_EQUALS: {"label": "no es igual a", "requiresValue": True},
    Operator.CONTAINS: {"label": "contiene", "requiresValue": True},
    Operator.GREATER_THAN: {"label": "mayor que", "requiresValue": True},
    Operator.LESS_THAN: {"label": "menor que", "requiresValue": True},
    Operator.GREATER_OR_EQUAL: {"label": "mayor o igual a", "requiresValue": True},
    Operator.LESS_OR_EQUAL: {"label": "menor o igual a", "requiresValue": True},
    Operator.BETWEEN: {"label": "entre", "requiresValue": True},
    Operator.IN: {"label": "es uno de", "requiresValue": True},
    Operator.NOT_IN: {"label": "no es uno de", "requiresValue": True},
    Operator.IS_NULL: {"label": "está vacío", "requiresValue": False},
    Operator.IS_NOT_NULL: {"label": "no está vacío", "requiresValue": False},
    Operator.DAYS_AGO_MORE_THAN: {"label": "hace más de X días", "requiresValue": True},
    Operator.DAYS_AGO_LESS_THAN: {"label": "hace menos de X días", "requiresValue": True},
}


@dataclass
class FilterField:
    """Define un campo filtrable."""
    key: str
    label: str
    field_type: FieldType
    db_field: str  # Campo real en la base de datos
    options: list[dict] = field(default_factory=list)  # Para SELECT/MULTI_SELECT
    help_text: str = ""
    
    def to_dict(self) -> dict:
        ops_list = []
        allowed_ops = OPERATORS_BY_TYPE.get(self.field_type, [])
        for op_enum in allowed_ops:
            meta = OPERATOR_DEFINITIONS.get(op_enum, {})
            ops_list.append({
                "id": op_enum.value,
                "label": meta.get("label", op_enum.value),
                "requiresValue": meta.get("requiresValue", True)
            })

        return {
            "id": self.key,
            "label": self.label,
            "type": self.field_type.value,
            "operators": ops_list,
            "options": self.options,
            "helpText": self.help_text,
        }


@dataclass 
class EntitySchema:
    """Define una entidad consultable."""
    key: str
    label: str
    icon: str
    description: str
    filters: list[FilterField]
    default_ordering: str = "-created_at"
    
    def to_dict(self) -> dict:
        return {
            "id": self.key,
            "name": self.label,
            "icon": self.icon,
            "description": self.description,
            "fields": [f.to_dict() for f in self.filters],
            "defaultOrdering": self.default_ordering,
        }


# =============================================================================
# DEFINICIÓN DE ENTIDADES Y FILTROS
# =============================================================================

# Opciones para selectores
USER_ROLE_OPTIONS = [
    {"value": "CLIENT", "label": "Cliente"},
    {"value": "VIP", "label": "VIP"},
    {"value": "STAFF", "label": "Staff"},
    {"value": "ADMIN", "label": "Administrador"},
]

APPOINTMENT_STATUS_OPTIONS = [
    {"value": "PENDING_PAYMENT", "label": "Pendiente de Pago"},
    {"value": "PAID", "label": "Pagado"},
    {"value": "CONFIRMED", "label": "Confirmada"},
    {"value": "RESCHEDULED", "label": "Reagendada"},
    {"value": "COMPLETED", "label": "Completada"},
    {"value": "CANCELLED", "label": "Cancelada"},
]

APPOINTMENT_OUTCOME_OPTIONS = [
    {"value": "NONE", "label": "Sin resultado"},
    {"value": "CANCELLED_BY_CLIENT", "label": "Cancelada por Cliente"},
    {"value": "CANCELLED_BY_SYSTEM", "label": "Cancelada por Sistema"},
    {"value": "CANCELLED_BY_ADMIN", "label": "Cancelada por Admin"},
    {"value": "NO_SHOW", "label": "No Asistió"},
    {"value": "REFUNDED", "label": "Reembolsada"},
]

PAYMENT_STATUS_OPTIONS = [
    {"value": "PENDING", "label": "Pendiente"},
    {"value": "APPROVED", "label": "Aprobado"},
    {"value": "DECLINED", "label": "Declinado"},
    {"value": "ERROR", "label": "Error"},
    {"value": "TIMEOUT", "label": "Sin confirmación"},
]

PAYMENT_TYPE_OPTIONS = [
    {"value": "ADVANCE", "label": "Anticipo de Cita"},
    {"value": "FINAL", "label": "Pago Final"},
    {"value": "PACKAGE", "label": "Compra de Paquete"},
    {"value": "TIP", "label": "Propina"},
    {"value": "VIP_SUBSCRIPTION", "label": "Membresía VIP"},
    {"value": "ORDER", "label": "Orden Marketplace"},
]

ORDER_STATUS_OPTIONS = [
    {"value": "PENDING_PAYMENT", "label": "Pendiente de Pago"},
    {"value": "PAID", "label": "Pagada"},
    {"value": "PREPARING", "label": "En Preparación"},
    {"value": "SHIPPED", "label": "Enviada"},
    {"value": "DELIVERED", "label": "Entregada"},
    {"value": "CANCELLED", "label": "Cancelada"},
    {"value": "RETURN_REQUESTED", "label": "Devolución Solicitada"},
    {"value": "REFUNDED", "label": "Reembolsada"},
]

DELIVERY_OPTIONS = [
    {"value": "PICKUP", "label": "Recogida en Local"},
    {"value": "DELIVERY", "label": "Envío a Domicilio"},
]


# -----------------------------------------------------------------------------
# ENTIDAD: CLIENTES
# -----------------------------------------------------------------------------
CLIENTS_ENTITY = EntitySchema(
    key="clients",
    label="Clientes",
    icon="👤",
    description="Consulta de clientes y usuarios VIP",
    default_ordering="-created_at",
    filters=[
        FilterField(
            key="role",
            label="Rol",
            field_type=FieldType.SELECT,
            db_field="role",
            options=USER_ROLE_OPTIONS,
        ),
        FilterField(
            key="is_vip_active",
            label="Es VIP Activo",
            field_type=FieldType.BOOLEAN,
            db_field="__computed_is_vip",
            help_text="Usuario con membresía VIP vigente",
        ),
        FilterField(
            key="vip_expires_at",
            label="VIP Expira",
            field_type=FieldType.DATE,
            db_field="vip_expires_at",
        ),
        FilterField(
            key="date_joined",
            label="Fecha de Registro",
            field_type=FieldType.DATE,
            db_field="created_at",
        ),
        FilterField(
            key="last_appointment_date",
            label="Última Cita",
            field_type=FieldType.DATE,
            db_field="__computed_last_appointment",
            help_text="Fecha de la última cita completada",
        ),
        FilterField(
            key="total_appointments",
            label="Total Citas",
            field_type=FieldType.NUMBER,
            db_field="__computed_total_appointments",
        ),
        FilterField(
            key="completed_appointments",
            label="Citas Completadas",
            field_type=FieldType.NUMBER,
            db_field="__computed_completed_appointments",
        ),
        FilterField(
            key="total_spent",
            label="Total Gastado",
            field_type=FieldType.MONEY,
            db_field="__computed_total_spent",
        ),
        FilterField(
            key="is_persona_non_grata",
            label="Bloqueado",
            field_type=FieldType.BOOLEAN,
            db_field="is_persona_non_grata",
        ),
        FilterField(
            key="has_email",
            label="Tiene Email",
            field_type=FieldType.BOOLEAN,
            db_field="__computed_has_email",
        ),
        FilterField(
            key="search",
            label="Buscar",
            field_type=FieldType.TEXT,
            db_field="__search",
            help_text="Busca por nombre, email o teléfono",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: CITAS
# -----------------------------------------------------------------------------
APPOINTMENTS_ENTITY = EntitySchema(
    key="appointments",
    label="Citas",
    icon="📅",
    description="Reservas y citas de servicios",
    default_ordering="-start_time",
    filters=[
        FilterField(
            key="status",
            label="Estado",
            field_type=FieldType.MULTI_SELECT,
            db_field="status",
            options=APPOINTMENT_STATUS_OPTIONS,
        ),
        FilterField(
            key="outcome",
            label="Resultado",
            field_type=FieldType.SELECT,
            db_field="outcome",
            options=APPOINTMENT_OUTCOME_OPTIONS,
        ),
        FilterField(
            key="date",
            label="Fecha",
            field_type=FieldType.DATE,
            db_field="start_time",
        ),
        FilterField(
            key="staff_member",
            label="Staff Asignado",
            field_type=FieldType.SELECT,
            db_field="staff_member_id",
            options=[],  # Se llena dinámicamente
        ),
        FilterField(
            key="total_amount",
            label="Monto Total",
            field_type=FieldType.MONEY,
            db_field="price_at_purchase",
        ),
        FilterField(
            key="reschedule_count",
            label="Reagendamientos",
            field_type=FieldType.NUMBER,
            db_field="reschedule_count",
        ),
        FilterField(
            key="client_search",
            label="Buscar Cliente",
            field_type=FieldType.TEXT,
            db_field="__client_search",
            help_text="Busca por nombre o teléfono del cliente",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: PAGOS
# -----------------------------------------------------------------------------
PAYMENTS_ENTITY = EntitySchema(
    key="payments",
    label="Pagos",
    icon="💳",
    description="Transacciones y pagos",
    default_ordering="-created_at",
    filters=[
        FilterField(
            key="status",
            label="Estado",
            field_type=FieldType.SELECT,
            db_field="status",
            options=PAYMENT_STATUS_OPTIONS,
        ),
        FilterField(
            key="payment_type",
            label="Tipo de Pago",
            field_type=FieldType.MULTI_SELECT,
            db_field="payment_type",
            options=PAYMENT_TYPE_OPTIONS,
        ),
        FilterField(
            key="amount",
            label="Monto",
            field_type=FieldType.MONEY,
            db_field="amount",
        ),
        FilterField(
            key="created_at",
            label="Fecha",
            field_type=FieldType.DATE,
            db_field="created_at",
        ),
        FilterField(
            key="client_search",
            label="Buscar Cliente",
            field_type=FieldType.TEXT,
            db_field="__client_search",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: ÓRDENES
# -----------------------------------------------------------------------------
ORDERS_ENTITY = EntitySchema(
    key="orders",
    label="Órdenes",
    icon="🛒",
    description="Compras del marketplace",
    default_ordering="-created_at",
    filters=[
        FilterField(
            key="status",
            label="Estado",
            field_type=FieldType.MULTI_SELECT,
            db_field="status",
            options=ORDER_STATUS_OPTIONS,
        ),
        FilterField(
            key="delivery_option",
            label="Tipo de Entrega",
            field_type=FieldType.SELECT,
            db_field="delivery_option",
            options=DELIVERY_OPTIONS,
        ),
        FilterField(
            key="total_amount",
            label="Monto Total",
            field_type=FieldType.MONEY,
            db_field="total_amount",
        ),
        FilterField(
            key="shipping_cost",
            label="Costo de Envío",
            field_type=FieldType.MONEY,
            db_field="shipping_cost",
        ),
        FilterField(
            key="created_at",
            label="Fecha",
            field_type=FieldType.DATE,
            db_field="created_at",
        ),
        FilterField(
            key="client_search",
            label="Buscar Cliente",
            field_type=FieldType.TEXT,
            db_field="__client_search",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: SERVICIOS
# -----------------------------------------------------------------------------
SERVICES_ENTITY = EntitySchema(
    key="services",
    label="Servicios",
    icon="💆",
    description="Catálogo de servicios",
    default_ordering="name",
    filters=[
        FilterField(
            key="category",
            label="Categoría",
            field_type=FieldType.SELECT,
            db_field="category_id",
            options=[],  # Se llena dinámicamente
        ),
        FilterField(
            key="price",
            label="Precio",
            field_type=FieldType.MONEY,
            db_field="price",
        ),
        FilterField(
            key="duration",
            label="Duración (minutos)",
            field_type=FieldType.NUMBER,
            db_field="duration",
        ),
        FilterField(
            key="is_active",
            label="Activo",
            field_type=FieldType.BOOLEAN,
            db_field="is_active",
        ),
        FilterField(
            key="search",
            label="Buscar",
            field_type=FieldType.TEXT,
            db_field="__search",
        ),
    ],
)

ALL_ENTITIES = [
    CLIENTS_ENTITY,
    APPOINTMENTS_ENTITY,
    PAYMENTS_ENTITY,
    ORDERS_ENTITY,
    SERVICES_ENTITY,
]

ENTITIES_BY_KEY = {entity.key: entity for entity in ALL_ENTITIES}


def get_full_schema() -> dict:
    """Retorna el schema completo para el frontend."""
    return {
        "entities": [entity.to_dict() for entity in ALL_ENTITIES],
        "aggregations": [
            {"key": "count", "label": "Contar registros"},
            {"key": "sum", "label": "Sumar"},
            {"key": "avg", "label": "Promedio"},
            {"key": "min", "label": "Mínimo"},
            {"key": "max", "label": "Máximo"},
        ],
        "groupBy": [
            {"key": "day", "label": "Por día"},
            {"key": "week", "label": "Por semana"},
            {"key": "month", "label": "Por mes"},
            {"key": "year", "label": "Por año"},
        ],
    }
