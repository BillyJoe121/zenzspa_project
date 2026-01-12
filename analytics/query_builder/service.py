"""
Query Builder Service - Ejecuta queries dinámicas de forma segura.

Este servicio toma la configuración del Query Builder y la convierte
en queries Django ORM, evitando SQL injection.
"""
import logging

from analytics.query_builder.aggregation import QueryBuilderAggregationMixin
from analytics.query_builder.base import QueryBuilderBase
from analytics.query_builder.filtering import QueryBuilderFilteringMixin
from analytics.query_builder.serialization import QueryBuilderSerializationMixin

logger = logging.getLogger(__name__)


class QueryBuilderService(
    QueryBuilderSerializationMixin,
    QueryBuilderAggregationMixin,
    QueryBuilderFilteringMixin,
    QueryBuilderBase,
):
    """Servicio para ejecutar queries dinámicas del Query Builder."""

    def execute(self) -> dict:
        """Ejecuta la query y retorna los resultados."""
        try:
            queryset = self._build_queryset()

            # Aplicar filtros
            for filter_config in self.filters:
                queryset = self._apply_filter(queryset, filter_config)

            # Si hay agregación con group_by
            if self.aggregation and self.group_by:
                return self._execute_grouped_aggregation(queryset)

            # Si hay agregación simple
            if self.aggregation:
                return self._execute_simple_aggregation(queryset)

            # Query normal con resultados
            return self._execute_list_query(queryset)

        except Exception as e:
            logger.error("Error en Query Builder: %s", str(e), exc_info=True)
            raise ValueError(f"Error al ejecutar la consulta: {str(e)}")


__all__ = ["QueryBuilderService"]
