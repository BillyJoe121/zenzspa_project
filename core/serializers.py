from rest_framework import serializers


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    Un ModelSerializer que elimina campos dinámicamente basados en el rol del usuario.

    Para usarlo, define un diccionario `role_based_fields` en la clase Meta del serializador hijo.
    Este diccionario mapea un rol a una lista de campos que SOLO los usuarios con ese rol (o superior) pueden ver.

    Ejemplo en la clase Meta de un serializador hijo:
    role_based_fields = {
        'STAFF': ['campo_privado_staff'],
        'ADMIN': ['campo_super_secreto_admin']
    }
    """

    def __init__(self, *args, **kwargs):
        # Llama al __init__ original
        super().__init__(*args, **kwargs)

        # Si no hay un request en el contexto, no podemos hacer nada.
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return

        user = request.user

        # Jerarquía de roles: un rol superior puede ver los campos de los roles inferiores.
        allowed_roles = {
            'CLIENT': ['CLIENT'],
            'VIP': ['CLIENT', 'VIP'],
            'STAFF': ['CLIENT', 'VIP', 'STAFF'],
            'ADMIN': ['CLIENT', 'VIP', 'STAFF', 'ADMIN']
        }
        user_allowed_set = set(allowed_roles.get(user.role, []))

        # Obtenemos la configuración de campos por rol del serializador hijo.
        # CORRECCIÓN: Añadimos un comentario para que Pylint ignore este falso positivo.
        # La clase Meta existirá en las subclases que hereden de esta.
        role_config = getattr(self.Meta, 'role_based_fields', # pylint: disable=no-member
                              {})  # pylint: disable=no-member

        # Iteramos sobre la configuración de campos restringidos
        for role, fields in role_config.items():
            # Si el rol requerido no está en los roles permitidos para el usuario actual...
            if role not in user_allowed_set:
                # ...eliminamos esos campos del serializador.
                for field_name in fields:
                    self.fields.pop(field_name, None)
