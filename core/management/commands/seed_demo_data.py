from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from marketplace.models import Product, ProductVariant
from notifications.models import NotificationPreference
from profiles.models import ClinicalProfile
from rest_framework_simplejwt.tokens import RefreshToken
from spa.models import Service, ServiceCategory
from users.utils import register_user_session

from .seed_demo_fixtures import (
    DEMO_USERS,
    MARKETPLACE_PRODUCTS,
    PRODUCT_CATEGORIES,
    SERVICE_CATALOG,
)


class Command(BaseCommand):
    help = "Crea data demo básica para catálogos de servicios, marketplace y usuarios autenticados."

    def handle(self, *args, **options):
        # Seed de categorías de productos FUERA de la transacción para evitar problemas de isolation
        product_category_map = self._seed_product_categories()

        with transaction.atomic():
            service_category_map, services_stats = self._seed_service_catalog()
            product_stats = self._seed_marketplace_products(product_category_map)
            user_stats, token_table = self._seed_users()

        self.stdout.write(self.style.SUCCESS("Seed de datos demo completado."))
        self.stdout.write("")
        self.stdout.write("Catálogo de servicios:")
        self.stdout.write(f"  Categorías creadas/actualizadas: {len(service_category_map)}")
        self.stdout.write(
            f"  Servicios procesados: {services_stats['processed']} (nuevos: {services_stats['created']})"
        )
        self.stdout.write("")
        self.stdout.write("Marketplace:")
        self.stdout.write(f"  Categorías de productos: {len(product_category_map)}")
        self.stdout.write(
            f"  Productos procesados: {product_stats['products_processed']} (nuevos: {product_stats['products_created']})"
        )
        self.stdout.write(
            f"  Variantes procesadas: {product_stats['variants_processed']} (nuevas: {product_stats['variants_created']})"
        )
        self.stdout.write("")
        self.stdout.write("Usuarios demo:")
        self.stdout.write(f"  Nuevos: {user_stats['created']} / Actualizados: {user_stats['updated']}")
        self.stdout.write("  Credenciales disponibles para pruebas manuales:")
        for entry in token_table:
            self.stdout.write("  - {label} ({role})".format(**entry))
            self.stdout.write(f"    Teléfono: {entry['phone_number']} | Password: {entry['password']}")
            self.stdout.write(f"    JWT Access: {entry['access']}")
            self.stdout.write(f"    JWT Refresh: {entry['refresh']}")
        self.stdout.write("")
        self.stdout.write(
            "Usa estos usuarios para autenticarte vía `/api/v1/auth/token/` o directamente con los JWT impresos."
        )

    def _seed_service_catalog(self):
        """
        Crea categorías y servicios de masajes reutilizando nombres como llave idempotente.
        Maneja correctamente SoftDeleteModel usando all_objects.
        """
        category_map = {}
        services_processed = 0
        services_created = 0

        for category_data in SERVICE_CATALOG:
            category_defaults = {
                "description": category_data["description"],
                "is_low_supervision": category_data.get("is_low_supervision", False),
            }

            category = ServiceCategory.all_objects.filter(name=category_data["name"]).first()
            if not category:
                category = ServiceCategory.objects.create(
                    name=category_data["name"],
                    **category_defaults
                )
            else:
                if category.is_deleted:
                    category.restore()

                updated_fields = []
                for field, value in category_defaults.items():
                    if getattr(category, field) != value:
                        setattr(category, field, value)
                        updated_fields.append(field)
                if updated_fields:
                    category.save(update_fields=updated_fields + ["updated_at"])

            category_map[category_data["key"]] = category

            for service_data in category_data["services"]:
                services_processed += 1
                defaults = {
                    "description": service_data["description"],
                    "duration": service_data["duration"],
                    "price": Decimal(service_data["price"]),
                    "vip_price": Decimal(service_data["vip_price"]),
                    "is_active": True,
                    "what_is_included": service_data.get("what_is_included", ""),
                    "benefits": service_data.get("benefits", ""),
                    "contraindications": service_data.get("contraindications", ""),
                }

                service = Service.all_objects.filter(name=service_data["name"], category=category).first()
                if not service:
                    Service.objects.create(
                        name=service_data["name"],
                        category=category,
                        **defaults
                    )
                    services_created += 1
                else:
                    if service.is_deleted:
                        service.restore()

                    updated_svc = False
                    for k, v in defaults.items():
                        if getattr(service, k) != v:
                            setattr(service, k, v)
                            updated_svc = True
                    if updated_svc:
                        service.save()

        return category_map, {"processed": services_processed, "created": services_created}

    def _seed_product_categories(self):
        """
        Crea las categorías de productos. Se ejecuta FUERA de transaction.atomic()
        para evitar problemas de isolation level en Postgres.
        Maneja correctamente SoftDeleteModel usando all_objects.
        """
        category_map = {}
        for key, cat_data in PRODUCT_CATEGORIES.items():
            category = ServiceCategory.all_objects.filter(name=cat_data["name"]).first()

            if not category:
                category = ServiceCategory.objects.create(
                    name=cat_data["name"],
                    description=cat_data["description"],
                    is_low_supervision=cat_data["is_low_supervision"]
                )
            else:
                if category.is_deleted:
                    category.restore()

                category.description = cat_data["description"]
                category.is_low_supervision = cat_data["is_low_supervision"]
                category.save(update_fields=['description', 'is_low_supervision', 'updated_at'])

            category_map[key] = category

        return category_map

    def _seed_marketplace_products(self, category_map):
        """
        Registra productos y variantes usando los SKUs como identificadores idempotentes.
        Recibe el category_map ya creado por _seed_product_categories().
        """

        products_processed = 0
        products_created = 0
        variants_processed = 0
        variants_created = 0

        for product_data in MARKETPLACE_PRODUCTS:
            category = category_map.get(product_data["category_key"])
            product_defaults = {
                "description": product_data["description"],
                "category": category,
                "preparation_days": product_data.get("preparation_days", 1),
                "is_active": product_data.get("is_active", True),
                "what_is_included": product_data.get("what_is_included", ""),
                "benefits": product_data.get("benefits", ""),
                "how_to_use": product_data.get("how_to_use", ""),
            }
            products_processed += 1
            product, created_product = Product.objects.update_or_create(
                name=product_data["name"],
                defaults=product_defaults,
            )
            if created_product:
                products_created += 1

            for variant_data in product_data["variants"]:
                variants_processed += 1
                defaults = {
                    "product": product,
                    "name": variant_data["name"],
                    "price": Decimal(variant_data["price"]),
                    "vip_price": Decimal(variant_data["vip_price"]) if variant_data.get("vip_price") else None,
                    "stock": variant_data.get("stock", 0),
                    "min_order_quantity": variant_data.get("min_order_quantity", 1),
                    "max_order_quantity": variant_data.get("max_order_quantity"),
                }
                _, created_variant = ProductVariant.objects.update_or_create(
                    sku=variant_data["sku"],
                    defaults=defaults,
                )
                if created_variant:
                    variants_created += 1

        return {
            "products_processed": products_processed,
            "products_created": products_created,
            "variants_processed": variants_processed,
            "variants_created": variants_created,
        }

    def _seed_users(self):
        """
        Crea dos trabajadores y dos clientes con tokens vigentes.
        """
        user_model = get_user_model()
        created_count = 0
        updated_count = 0
        token_table = []

        for user_info in DEMO_USERS:
            user = user_model.objects.filter(phone_number=user_info["phone_number"]).first()
            base_kwargs = {
                "email": user_info["email"],
                "first_name": user_info["first_name"],
                "last_name": user_info["last_name"],
                "role": user_info["role"],
                "is_staff": user_info["is_staff"],
                "is_verified": user_info["is_verified"],
                "internal_notes": user_info.get("internal_notes", ""),
            }
            if user is None:
                user = user_model.objects.create_user(
                    phone_number=user_info["phone_number"],
                    email=user_info["email"],
                    first_name=user_info["first_name"],
                    password=user_info["password"],
                    last_name=user_info["last_name"],
                    role=user_info["role"],
                    is_staff=user_info["is_staff"],
                    is_verified=user_info["is_verified"],
                    internal_notes=user_info.get("internal_notes", ""),
                )
                created_count += 1
            else:
                changed = False
                for field, value in base_kwargs.items():
                    if getattr(user, field) != value:
                        setattr(user, field, value)
                        changed = True
                if not user.check_password(user_info["password"]):
                    user.set_password(user_info["password"])
                    changed = True
                if changed:
                    user.save()
                    updated_count += 1

            ClinicalProfile.objects.get_or_create(user=user)
            NotificationPreference.for_user(user)

            if user_info.get("issue_tokens", False):
                refresh = RefreshToken.for_user(user)
                register_user_session(
                    user=user,
                    refresh_token_jti=str(refresh["jti"]),
                    ip_address="127.0.0.1",
                    user_agent="seed-demo-script",
                    sender=self.__class__,
                )
                token_table.append(
                    {
                        "label": user_info["label"],
                        "role": user.role,
                        "phone_number": user.phone_number,
                        "password": user_info["password"],
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    }
                )

        return {"created": created_count, "updated": updated_count}, token_table


__all__ = ["Command"]
