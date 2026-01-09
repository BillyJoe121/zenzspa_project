"""
Query Builder - Schema principal.

Define y reexporta los tipos, modelos, opciones y entidades disponibles para
construir queries dinámicas desde el frontend.
"""
from analytics.query_builder.types import (
    FieldType,
    Operator,
    OPERATORS_BY_TYPE,
    OPERATOR_DEFINITIONS,
)
from analytics.query_builder.models import FilterField, EntitySchema
from analytics.query_builder.options import (
    USER_ROLE_OPTIONS,
    APPOINTMENT_STATUS_OPTIONS,
    APPOINTMENT_OUTCOME_OPTIONS,
    PAYMENT_STATUS_OPTIONS,
    PAYMENT_TYPE_OPTIONS,
    ORDER_STATUS_OPTIONS,
    DELIVERY_OPTIONS,
)
from analytics.query_builder.entities import (
    CLIENTS_ENTITY,
    APPOINTMENTS_ENTITY,
    PAYMENTS_ENTITY,
    ORDERS_ENTITY,
    SERVICES_ENTITY,
    ALL_ENTITIES,
)

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


__all__ = [
    "FieldType",
    "Operator",
    "OPERATORS_BY_TYPE",
    "OPERATOR_DEFINITIONS",
    "FilterField",
    "EntitySchema",
    "USER_ROLE_OPTIONS",
    "APPOINTMENT_STATUS_OPTIONS",
    "APPOINTMENT_OUTCOME_OPTIONS",
    "PAYMENT_STATUS_OPTIONS",
    "PAYMENT_TYPE_OPTIONS",
    "ORDER_STATUS_OPTIONS",
    "DELIVERY_OPTIONS",
    "CLIENTS_ENTITY",
    "APPOINTMENTS_ENTITY",
    "PAYMENTS_ENTITY",
    "ORDERS_ENTITY",
    "SERVICES_ENTITY",
    "ALL_ENTITIES",
    "ENTITIES_BY_KEY",
    "get_full_schema",
]
