from rest_framework import serializers
from .models import Promocion


class PromocionSerializer(serializers.ModelSerializer):
    """
    Serializer para promociones que se mostrará al frontend.
    Solo incluye campos necesarios para la visualización.
    """
    esta_vigente = serializers.SerializerMethodField()

    class Meta:
        model = Promocion
        fields = [
            'id', 'titulo', 'descripcion', 'imagen', 'imagen_url',
            'tipo', 'paginas', 'mostrar_siempre', 'link_accion',
            'texto_boton', 'esta_vigente', 'activa', 'fecha_inicio', 'fecha_fin',
        ]

    def to_internal_value(self, data):
        """
        Pre-procesamiento para manejar datos enviados vía FormData (Multipart).
        Convierte strings de booleano y JSON a tipos nativos de Python.
        """
        # Clonar datos para poder modificarlos si es un QueryDict
        if hasattr(data, 'dict'):
            data = data.dict()
        else:
            data = data.copy() if isinstance(data, dict) else data

        # 1. Manejar booleano 'activa' (de string a bool)
        if 'activa' in data:
            val = data['activa']
            if isinstance(val, str):
                data['activa'] = val.lower() in ('true', '1', 'yes', 't')

        # 2. Manejar booleano 'mostrar_siempre'
        if 'mostrar_siempre' in data:
            val = data['mostrar_siempre']
            if isinstance(val, str):
                data['mostrar_siempre'] = val.lower() in ('true', '1', 'yes', 't')

        # 3. Manejar lista 'paginas' (de string JSON/CSV a list)
        if 'paginas' in data:
            val = data['paginas']
            if isinstance(val, str):
                import json
                try:
                    # Intentar cargar como JSON por si viene stringified
                    parsed = json.loads(val.replace("'", '"'))
                    data['paginas'] = parsed if isinstance(parsed, list) else [val]
                except (json.JSONDecodeError, ValueError):
                    # Fallback a lista separada por comas
                    data['paginas'] = [x.strip() for x in val.split(',') if x.strip()]

        # 4. Manejar fechas vacías (de "" a None)
        for date_field in ['fecha_inicio', 'fecha_fin']:
            if date_field in data and data[date_field] == '':
                data[date_field] = None

        return super().to_internal_value(data)

    def get_esta_vigente(self, obj):
        """Retorna si la promoción está vigente."""
        return obj.esta_vigente()


class PromocionListSerializer(serializers.ModelSerializer):
    """
    Serializer simplificado para listar promociones (sin descripción completa).
    Útil para endpoints que devuelven múltiples promociones.
    """
    class Meta:
        model = Promocion
        fields = [
            'id',
            'titulo',
            'imagen',
            'imagen_url',
            'tipo',
            'link_accion',
            'texto_boton',
        ]
