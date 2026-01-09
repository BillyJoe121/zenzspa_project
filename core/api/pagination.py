"""
Core API - Pagination.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class DefaultPageNumberPagination(PageNumberPagination):
    """
    Paginación estándar por número de página con metadata enriquecida.

    Configuración:
    - page_size: 20 items por página (default)
    - page_size_query_param: Permite al cliente ajustar con ?page_size=N
    - max_page_size: Máximo 100 items por página

    Formato de respuesta:
        {
            "count": <total de items>,
            "page": <número de página actual>,
            "pages": <total de páginas>,
            "results": [<items de la página>]
        }

    Uso:
        class MyViewSet(viewsets.ModelViewSet):
            pagination_class = DefaultPageNumberPagination
    """
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        """
        Construye la respuesta paginada con metadata extendida.

        Args:
            data: Lista de items serializados para la página actual.

        Returns:
            Response: Objeto Response con estructura estándar de paginación.
        """
        return Response({
            "count": self.page.paginator.count,
            "page": self.page.number,
            "pages": self.page.paginator.num_pages,
            "results": data,
        })
