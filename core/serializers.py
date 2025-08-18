from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence
from rest_framework import serializers


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    ModelSerializer que oculta campos dinámicamente según el rol del usuario.

    Cómo funciona:
      - Define en Meta.role_based_fields un dict {ROL: [campos]} indicando
        qué campos SOLO están visibles para ese rol (y roles superiores).
      - La jerarquía es: CLIENT < VIP < STAFF < ADMIN.
      - Si el request no existe o el usuario no está autenticado, se asume CLIENT.

    También respeta, si se proveen en context:
      - context['include_fields']: lista blanca explícita de campos a mantener.
      - context['exclude_fields']: lista negra explícita de campos a remover.
    """

    ROLE_HIERARCHY: Dict[str, Sequence[str]] = {
        "CLIENT": ("CLIENT",),
        "VIP": ("CLIENT", "VIP"),
        "STAFF": ("CLIENT", "VIP", "STAFF"),
        "ADMIN": ("CLIENT", "VIP", "STAFF", "ADMIN"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        user_role = getattr(getattr(request, "user", None), "role", "CLIENT") or "CLIENT"
        allowed_roles = set(self.ROLE_HIERARCHY.get(user_role, ("CLIENT",)))

        # Listas de control opcionales desde el contexto
        include_fields: Optional[Iterable[str]] = self.context.get("include_fields")
        exclude_fields: Optional[Iterable[str]] = self.context.get("exclude_fields")

        # 1) Aplica include_fields si está definida (lista blanca)
        if include_fields:
            include_set = set(include_fields)
            for field_name in list(self.fields.keys()):
                if field_name not in include_set:
                    self.fields.pop(field_name, None)

        # 2) Aplica exclude_fields explícitos
        if exclude_fields:
            for field_name in exclude_fields:
                self.fields.pop(field_name, None)

        # 3) Aplica visibilidad por rol definida en el Meta del hijo
        role_config: Dict[str, List[str]] = getattr(self.Meta, "role_based_fields", {})  # type: ignore[attr-defined]
        if role_config:
            # Si el usuario NO tiene un rol requerido para ver ciertos campos, se ocultan
            for required_role, fields in role_config.items():
                if required_role not in allowed_roles:
                    for field_name in fields:
                        self.fields.pop(field_name, None)
