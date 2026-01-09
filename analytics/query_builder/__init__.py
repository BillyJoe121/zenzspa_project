"""
Paquete Query Builder de Analytics.

Este paquete proporciona un sistema de construcción de queries dinámico
para el panel administrativo.

Exporta:
- QueryBuilderService: Servicio principal para ejecutar queries
- get_full_schema: Función para obtener el schema completo del frontend
- ENTITIES_BY_KEY: Diccionario de entidades por clave
- Todos los tipos, modelos, opciones y entidades
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
from analytics.query_builder.schema import (
    ENTITIES_BY_KEY,
    get_full_schema,
)
from analytics.query_builder.service import QueryBuilderService


__all__ = [
    # Types
    "FieldType",
    "Operator",
    "OPERATORS_BY_TYPE",
    "OPERATOR_DEFINITIONS",
    # Models
    "FilterField",
    "EntitySchema",
    # Options
    "USER_ROLE_OPTIONS",
    "APPOINTMENT_STATUS_OPTIONS",
    "APPOINTMENT_OUTCOME_OPTIONS",
    "PAYMENT_STATUS_OPTIONS",
    "PAYMENT_TYPE_OPTIONS",
    "ORDER_STATUS_OPTIONS",
    "DELIVERY_OPTIONS",
    # Entities
    "CLIENTS_ENTITY",
    "APPOINTMENTS_ENTITY",
    "PAYMENTS_ENTITY",
    "ORDERS_ENTITY",
    "SERVICES_ENTITY",
    "ALL_ENTITIES",
    "ENTITIES_BY_KEY",
    # Functions & Services
    "get_full_schema",
    "QueryBuilderService",
]
