"""
Fachada de fixtures para seed_demo_data.

Mantiene nombres originales importando desde módulos segmentados.
"""
from .seed_demo_services import SERVICE_CATALOG
from .seed_demo_products import PRODUCT_CATEGORIES, MARKETPLACE_PRODUCTS
from .seed_demo_users import DEMO_USERS

__all__ = [
    "SERVICE_CATALOG",
    "PRODUCT_CATEGORIES",
    "MARKETPLACE_PRODUCTS",
    "DEMO_USERS",
]
