"""
Query Builder - Modelos de datos.
"""
from dataclasses import dataclass, field

from analytics.query_builder.types import FieldType, OPERATORS_BY_TYPE, OPERATOR_DEFINITIONS


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
