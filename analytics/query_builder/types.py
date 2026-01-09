"""
Query Builder - Tipos y constantes.
"""
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
