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


SERVICE_CATALOG = [
    {
        "key": "relax",
        "name": "Masajes Relajantes",
        "description": "Protocolos suaves con aromaterapia para liberar tensión y promover descanso profundo.",
        "is_low_supervision": True,
        "services": [
            {
                "name": "Masaje Sueco Restaurador",
                "description": "Técnica clásica de movimientos largos y presión ligera con aceites herbales cálidos.",
                "duration": 60,
                "price": "120000.00",
                "vip_price": "98000.00",
            },
            {
                "name": "Masaje con Aromaterapia",
                "description": "Sesión sensorial con aceites esenciales personalizados para balance emocional.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "115000.00",
            },
        ],
    },
    {
        "key": "terapeuticos",
        "name": "Masajes Terapéuticos",
        "description": "Tratamientos profundos para deportistas y clientes con puntos de tensión crónica.",
        "is_low_supervision": False,
        "services": [
            {
                "name": "Masaje Descontracturante Profundo",
                "description": "Trabajo específico en fascias y tejido profundo para liberar nudos musculares.",
                "duration": 50,
                "price": "135000.00",
                "vip_price": "110000.00",
            },
            {
                "name": "Masaje Deportivo de Recuperación",
                "description": "Combinación de liberación miofascial y stretching para atletas en post competencia.",
                "duration": 45,
                "price": "118000.00",
                "vip_price": "99000.00",
            },
        ],
    },
    {
        "key": "ritual",
        "name": "Rituales Sensoriales",
        "description": "Experiencias completas que combinan masaje, exfoliación y meditación guiada.",
        "is_low_supervision": False,
        "services": [
            {
                "name": "Ritual de Piedras Calientes",
                "description": "Secuencia con rocas volcánicas para calmar el sistema nervioso y mejorar la circulación.",
                "duration": 90,
                "price": "195000.00",
                "vip_price": "165000.00",
            },
        ],
    },
]

MARKETPLACE_PRODUCTS = [
    {
        "name": "Kit de Aromaterapia Relax",
        "category_key": "relax",
        "description": "Colección de aceites esenciales inspirados en nuestros masajes relajantes.",
        "preparation_days": 1,
        "is_active": True,
        "variants": [
            {
                "name": "3 aceites de 15ml",
                "sku": "AROMA-KIT-03",
                "price": "85000.00",
                "vip_price": "78000.00",
                "stock": 18,
                "min_order_quantity": 1,
                "max_order_quantity": 3,
            },
            {
                "name": "6 aceites de 15ml",
                "sku": "AROMA-KIT-06",
                "price": "155000.00",
                "vip_price": "139000.00",
                "stock": 10,
                "min_order_quantity": 1,
                "max_order_quantity": 2,
            },
        ],
    },
    {
        "name": "Bálsamo Terapéutico de Árnica",
        "category_key": "terapeuticos",
        "description": "Bálsamo de uso profesional para aliviar inflamación después de masajes profundos.",
        "preparation_days": 2,
        "is_active": True,
        "variants": [
            {
                "name": "Tarro 60g",
                "sku": "BAL-ARNICA-60",
                "price": "68000.00",
                "vip_price": "62000.00",
                "stock": 25,
                "min_order_quantity": 1,
            },
            {
                "name": "Tarro 120g",
                "sku": "BAL-ARNICA-120",
                "price": "98000.00",
                "vip_price": "89000.00",
                "stock": 15,
                "min_order_quantity": 1,
            },
        ],
    },
    {
        "name": "Infusión Calma Nocturna",
        "category_key": "ritual",
        "description": "Mezcla de hierbas orgánicas para acompañar rituales de descanso y mindfulness.",
        "preparation_days": 1,
        "is_active": True,
        "variants": [
            {
                "name": "Caja 10 sobres",
                "sku": "INF-CALMA-10",
                "price": "45000.00",
                "vip_price": "39000.00",
                "stock": 30,
                "min_order_quantity": 1,
                "max_order_quantity": 5,
            },
        ],
    },
]

DEMO_USERS = [
    {
        "label": "Terapeuta Andrea",
        "phone_number": "+573102000001",
        "email": "andrea.demo@studiozens.test",
        "first_name": "Andrea",
        "last_name": "Calma",
        "role": "STAFF",
        "is_staff": True,
        "is_verified": True,
        "password": "DemoStaff123!",
        "internal_notes": "Trabajadora demo creada por seed_demo_data.",
        "issue_tokens": True,
    },
    {
        "label": "Terapeuta Mateo",
        "phone_number": "+573102000002",
        "email": "mateo.demo@studiozens.test",
        "first_name": "Mateo",
        "last_name": "Balance",
        "role": "STAFF",
        "is_staff": True,
        "is_verified": True,
        "password": "DemoStaff123!",
        "internal_notes": "Trabajador demo creado por seed_demo_data.",
        "issue_tokens": True,
    },
    {
        "label": "Cliente Laura",
        "phone_number": "+573102000101",
        "email": "laura.demo@studiozens.test",
        "first_name": "Laura",
        "last_name": "Serenidad",
        "role": "CLIENT",
        "is_staff": False,
        "is_verified": True,
        "password": "DemoCliente123!",
        "internal_notes": "Cliente demo registrado y autenticado automáticamente.",
        "issue_tokens": True,
    },
    {
        "label": "Cliente David",
        "phone_number": "+573102000102",
        "email": "david.demo@studiozens.test",
        "first_name": "David",
        "last_name": "Vital",
        "role": "CLIENT",
        "is_staff": False,
        "is_verified": True,
        "password": "DemoCliente123!",
        "internal_notes": "Cliente demo registrado y autenticado automáticamente.",
        "issue_tokens": True,
    },
]


class Command(BaseCommand):
    help = "Crea data demo básica para catálogos de servicios, marketplace y usuarios autenticados."

    def handle(self, *args, **options):
        with transaction.atomic():
            category_map, services_stats = self._seed_service_catalog()
            product_stats = self._seed_marketplace(category_map)
            user_stats, token_table = self._seed_users()

        self.stdout.write(self.style.SUCCESS("Seed de datos demo completado."))
        self.stdout.write("")
        self.stdout.write("Catálogo de servicios:")
        self.stdout.write(f"  Categorías creadas/actualizadas: {len(category_map)}")
        self.stdout.write(
            f"  Servicios procesados: {services_stats['processed']} (nuevos: {services_stats['created']})"
        )
        self.stdout.write("")
        self.stdout.write("Marketplace:")
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
        self.stdout.write("Usa estos usuarios para autenticarte vía `/api/v1/auth/token/` o directamente con los JWT impresos.")

    def _seed_service_catalog(self):
        """
        Crea categorías y servicios de masajes reutilizando nombres como llave idempotente.
        """
        category_map = {}
        services_processed = 0
        services_created = 0

        for category_data in SERVICE_CATALOG:
            category_defaults = {
                "description": category_data["description"],
                "is_low_supervision": category_data.get("is_low_supervision", False),
            }
            category, created = ServiceCategory.objects.get_or_create(
                name=category_data["name"],
                defaults=category_defaults,
            )
            if not created:
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
                }
                _, created_service = Service.objects.update_or_create(
                    name=service_data["name"],
                    category=category,
                    defaults=defaults,
                )
                if created_service:
                    services_created += 1

        return category_map, {"processed": services_processed, "created": services_created}

    def _seed_marketplace(self, category_map):
        """
        Registra productos y variantes usando los SKUs como identificadores idempotentes.
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
