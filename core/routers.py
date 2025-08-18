from rest_framework.routers import DefaultRouter

def get_default_router() -> DefaultRouter:
    """
    Devuelve un router DRF con trailing_slash opcional homogéneo.
    """
    return DefaultRouter(trailing_slash=True)
