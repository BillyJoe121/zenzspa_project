"""
Query Builder - Agregaciones.
"""
from django.db.models import Count, Sum, Avg, Min, Max
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear


class QueryBuilderAggregationMixin:
    """Agrupaciones y agregaciones."""

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
