"""
Views Query Builder - Endpoints del Query Builder.
"""
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.permissions import CanViewAnalytics, CanViewFinancialMetrics
from analytics.throttling import AnalyticsRateThrottle
from analytics.views.shared import audit_analytics


class QueryBuilderSchemaView(APIView):
    """
    Endpoint para obtener el schema del Query Builder.
    Retorna todas las entidades, filtros y operadores disponibles.

    GET /api/v1/analytics/query-builder/schema/
    """
    permission_classes = [CanViewAnalytics]

    def get(self, request):
        from analytics.query_builder import get_full_schema, ENTITIES_BY_KEY
        from spa.models import ServiceCategory
        from users.models import CustomUser

        schema = get_full_schema()

        # Llenar opciones dinámicas

        # Staff options
        staff_members = CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True
        ).values("id", "first_name", "last_name")

        staff_options = [
            {"value": str(s["id"]), "label": f"{s['first_name']} {s['last_name']}".strip() or "Sin nombre"}
            for s in staff_members
        ]

        # Category options
        categories = ServiceCategory.objects.all().values("id", "name")
        category_options = [
            {"value": str(c["id"]), "label": c["name"]}
            for c in categories
        ]

        # Actualizar schema con opciones dinámicas
        for entity in schema["entities"]:
            for field_def in entity["fields"]:
                if field_def["id"] == "staff_member":
                    field_def["options"] = staff_options
                elif field_def["id"] == "category":
                    field_def["options"] = category_options

        audit_analytics(request, "query_builder_schema", {})
        return Response(schema)


class QueryBuilderExecuteView(APIView):
    """
    Endpoint para ejecutar queries del Query Builder.

    POST /api/v1/analytics/query-builder/execute/

    Body:
    {
        "entity": "clients",
        "filters": [
            {"field": "role", "operator": "equals", "value": "VIP"},
            {"field": "last_appointment_date", "operator": "days_ago_more_than", "value": 15}
        ],
        "ordering": "-total_appointments",
        "limit": 50,
        "aggregation": null,
        "groupBy": null
    }
    """
    permission_classes = [CanViewFinancialMetrics]  # Solo Admin puede ejecutar queries
    throttle_classes = [AnalyticsRateThrottle]

    def post(self, request):
        from analytics.query_builder import QueryBuilderService

        # Validar input
        entity = request.data.get("entity")
        if not entity:
            return Response({"error": "Se requiere el campo 'entity'"}, status=400)

        filters = request.data.get("filters", [])
        ordering = request.data.get("ordering")
        limit = request.data.get("limit", 100)
        aggregation = request.data.get("aggregation")
        group_by = request.data.get("groupBy")

        # Validar límite
        try:
            limit = int(limit)
            if limit < 1 or limit > 1000:
                raise ValueError()
        except (TypeError, ValueError):
            return Response({"error": "limit debe ser un número entre 1 y 1000"}, status=400)

        try:
            service = QueryBuilderService(
                entity_key=entity,
                filters=filters,
                ordering=ordering,
                limit=limit,
                aggregation=aggregation,
                group_by=group_by,
            )
            result = service.execute()

            audit_analytics(
                request,
                "query_builder_execute",
                {
                    "entity": entity,
                    "filters_count": len(filters),
                    "result_type": result.get("type"),
                    "result_count": result.get("count", result.get("value")),
                },
            )

            return Response(result)

        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error en Query Builder")
            return Response(
                {"error": "Error interno al ejecutar la consulta"},
                status=500
            )


class QueryBuilderPresetsView(APIView):
    """
    Endpoint para obtener y guardar presets de queries predefinidas.

    GET /api/v1/analytics/query-builder/presets/
    """
    permission_classes = [CanViewAnalytics]

    # Presets predefinidos (hardcoded)
    PRESETS = [
        {
            "id": "vip-most-bookings",
            "name": "VIPs con más reservas",
            "description": "Clientes VIP ordenados por total de citas",
            "icon": "👑",
            "config": {
                "entity": "clients",
                "filters": [
                    {"field": "role", "operator": "equals", "value": "VIP"}
                ],
                "ordering": "-completed_appointments",
                "limit": 20,
            }
        },
        {
            "id": "inactive-clients",
            "name": "Clientes inactivos (15 días)",
            "description": "Clientes sin citas en los últimos 15 días",
            "icon": "😴",
            "config": {
                "entity": "clients",
                "filters": [
                    {"field": "last_appointment_date", "operator": "days_ago_more_than", "value": 15}
                ],
                "ordering": "last_appointment_date",
                "limit": 50,
            }
        },
        {
            "id": "oldest-clients",
            "name": "Clientes más antiguos",
            "description": "Clientes ordenados por fecha de registro",
            "icon": "📅",
            "config": {
                "entity": "clients",
                "filters": [],
                "ordering": "date_joined",
                "limit": 50,
            }
        },
        {
            "id": "top-spenders",
            "name": "Mejores clientes (gasto)",
            "description": "Clientes con mayor gasto total",
            "icon": "💰",
            "config": {
                "entity": "clients",
                "filters": [],
                "ordering": "-total_spent",
                "limit": 20,
            }
        },
        {
            "id": "no-show-appointments",
            "name": "Citas con no-show",
            "description": "Citas donde el cliente no asistió",
            "icon": "❌",
            "config": {
                "entity": "appointments",
                "filters": [
                    {"field": "outcome", "operator": "equals", "value": "NO_SHOW"}
                ],
                "ordering": "-date",
                "limit": 50,
            }
        },
        {
            "id": "pending-deliveries",
            "name": "Órdenes pendientes de envío",
            "description": "Órdenes pagadas pendientes de preparar/enviar",
            "icon": "📦",
            "config": {
                "entity": "orders",
                "filters": [
                    {"field": "status", "operator": "in", "value": ["PAID", "PREPARING"]},
                    {"field": "delivery_option", "operator": "equals", "value": "DELIVERY"}
                ],
                "ordering": "-created_at",
                "limit": 50,
            }
        },
        {
            "id": "approved-payments-today",
            "name": "Pagos aprobados hoy",
            "description": "Pagos exitosos del día actual",
            "icon": "✅",
            "config": {
                "entity": "payments",
                "filters": [
                    {"field": "status", "operator": "equals", "value": "APPROVED"},
                    {"field": "created_at", "operator": "days_ago_less_than", "value": 1}
                ],
                "ordering": "-created_at",
                "limit": 100,
            }
        },
        {
            "id": "expiring-vip",
            "name": "VIPs por expirar (30 días)",
            "description": "Membresías VIP que expiran pronto",
            "icon": "⏰",
            "config": {
                "entity": "clients",
                "filters": [
                    {"field": "role", "operator": "equals", "value": "VIP"},
                    {"field": "vip_expires_at", "operator": "days_ago_less_than", "value": -30}
                ],
                "ordering": "vip_expires_at",
                "limit": 50,
            }
        },
    ]

    def get(self, request):
        audit_analytics(request, "query_builder_presets", {})
        return Response({"presets": self.PRESETS})
