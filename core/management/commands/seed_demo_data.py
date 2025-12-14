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
        "key": "integrales",
        "name": "Integrales",
        "description": "Terapias completas que trabajan todo el cuerpo para restaurar el equilibrio físico y energético.",
        "is_low_supervision": False,
        "services": [
            {
                "name": "Terapéutico Completo",
                "description": "Masaje terapéutico de cuerpo completo que combina técnicas de tejido profundo y relajación para liberar tensiones musculares y mejorar la circulación.",
                "duration": 90,
                "price": "150000.00",
                "vip_price": "135000.00",
            },
            {
                "name": "Terapéutico Focalizado",
                "description": "Tratamiento específico en zonas de mayor tensión como espalda, cuello y hombros, ideal para aliviar contracturas puntuales.",
                "duration": 50,
                "price": "130000.00",
                "vip_price": "117000.00",
            },
            {
                "name": "Terapéutico Mixto",
                "description": "Equilibrio perfecto entre terapia profunda en zonas críticas y masaje relajante en el resto del cuerpo.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "130000.00",
            },
        ],
    },
    {
        "key": "detox",
        "name": "Detox",
        "description": "Protocolos de desintoxicación que estimulan el sistema linfático y eliminan toxinas del organismo.",
        "is_low_supervision": False,
        "services": [
            {
                "name": "Drenaje Linfático",
                "description": "Técnica suave y rítmica que activa el sistema linfático para reducir retención de líquidos, mejorar la circulación y fortalecer el sistema inmune.",
                "duration": 60,
                "price": "140000.00",
                "vip_price": "126000.00",
            },
            {
                "name": "Terapia de Equilibrio",
                "description": "Tratamiento holístico que combina drenaje linfático con puntos de acupresión para restaurar el balance energético del cuerpo.",
                "duration": 75,
                "price": "155000.00",
                "vip_price": "139000.00",
            },
            {
                "name": "Udvartana",
                "description": "Masaje ayurvédico con polvos herbales que exfolia, tonifica y estimula la circulación mientras elimina toxinas acumuladas en la piel.",
                "duration": 90,
                "price": "170000.00",
                "vip_price": "153000.00",
            },
        ],
    },
    {
        "key": "spa",
        "name": "Spa",
        "description": "Experiencias sensoriales de relajación profunda y cuidado integral del cuerpo y la mente.",
        "is_low_supervision": True,
        "services": [
            {
                "name": "Experiencia Zen",
                "description": "Ritual de relajación que integra aromaterapia, música terapéutica y técnicas de masaje suaves para alcanzar un estado de calma profunda.",
                "duration": 60,
                "price": "135000.00",
                "vip_price": "121000.00",
            },
            {
                "name": "Zen Extendido",
                "description": "Versión extendida de la Experiencia Zen con mayor tiempo dedicado a cada zona del cuerpo y técnicas de meditación guiada.",
                "duration": 90,
                "price": "165000.00",
                "vip_price": "148000.00",
            },
            {
                "name": "Toque de Seda",
                "description": "Masaje delicado con aceites nutritivos que hidrata profundamente la piel mientras relaja el cuerpo con movimientos envolventes y sedosos.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "130000.00",
            },
            {
                "name": "Herbal Essence",
                "description": "Tratamiento revitalizante con aceites esenciales herbales de notas masculinas, combinando masaje profundo y aromaterapia energizante.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "130000.00",
            },
            {
                "name": "Cráneo Facial Ensueño",
                "description": "Masaje facial y craneal que libera tensiones acumuladas en rostro, cuero cabelludo y cuello, promoviendo relajación mental profunda.",
                "duration": 45,
                "price": "120000.00",
                "vip_price": "108000.00",
            },
            {
                "name": "Cráneo Facial Ocaso",
                "description": "Ritual vespertino que combina técnicas de acupresión facial con masaje craneal para aliviar el estrés del día y preparar el descanso.",
                "duration": 50,
                "price": "130000.00",
                "vip_price": "117000.00",
            },
            {
                "name": "Cráneo Facial Renacer",
                "description": "Tratamiento revitalizante que estimula puntos energéticos del rostro y cráneo para renovar la vitalidad y luminosidad de la piel.",
                "duration": 60,
                "price": "145000.00",
                "vip_price": "130000.00",
            },
            {
                "name": "Pediluvio",
                "description": "Baño terapéutico de pies con sales minerales y aceites esenciales, seguido de masaje reflexológico para activar puntos de bienestar.",
                "duration": 30,
                "price": "80000.00",
                "vip_price": "72000.00",
            },
            {
                "name": "Limpieza Facial Sencilla",
                "description": "Protocolo básico de limpieza profunda que elimina impurezas, exfolia suavemente y equilibra la piel del rostro.",
                "duration": 45,
                "price": "110000.00",
                "vip_price": "99000.00",
            },
            {
                "name": "Hidra Facial",
                "description": "Tratamiento facial avanzado con tecnología de hidrodermabrasión que limpia, exfolia e hidrata profundamente para una piel radiante.",
                "duration": 60,
                "price": "180000.00",
                "vip_price": "162000.00",
            },
        ],
    },
]

# ============================================================================
# CATÁLOGO DE PRODUCTOS REALES - MARKETPLACE
# ============================================================================
# Costos estimados incluyen: materia prima + envase + etiqueta/branding
# Precios VIP: 15% de descuento sobre precio regular
# ============================================================================

MARKETPLACE_PRODUCTS = [
    # ========================================================================
    # CATEGORÍA: AROMATERAPIA Y AMBIENTACIÓN
    # ========================================================================
    {
        "name": "Aceites Esenciales Puros",
        "category_key": "aromaterapia",
        "description": "Aceites esenciales 100% puros de grado terapéutico. Cada gota concentra la esencia botánica más pura para transformar tu hogar en un santuario de bienestar. Úsalos en difusores, baños aromáticos o masajes.",
        "preparation_days": 1,
        "is_active": True,
        "variants": [
            {
                "name": "Lavanda del Valle - 10ml",
                "sku": "AE-LAVANDA-10",
                "price": "42000.00",
                "vip_price": "37000.00",  # Costo aprox: $12k-15k (aceite + frasco ámbar + etiqueta)
                "stock": 40,
                "min_order_quantity": 1,
            },
            {
                "name": "Eucalipto & Menta - 10ml",
                "sku": "AE-EUCALIPTO-10",
                "price": "42000.00",
                "vip_price": "37000.00",  # Costo aprox: $12k-15k
                "stock": 35,
                "min_order_quantity": 1,
            },
            {
                "name": "Naranja Dulce - 10ml",
                "sku": "AE-NARANJA-10",
                "price": "39000.00",
                "vip_price": "35000.00",  # Costo aprox: $12k-15k
                "stock": 45,
                "min_order_quantity": 1,
            },
        ],
    },
    {
        "name": "Velas Aromáticas de Soja",
        "category_key": "aromaterapia",
        "description": "Velas artesanales vertidas a mano con cera de soja 100% natural y mechas de algodón. Sin parafina ni toxinas. Duración extendida y aromas sutiles que perfuman sin saturar. Cada vela es una pieza única.",
        "preparation_days": 2,
        "is_active": True,
        "variants": [
            {
                "name": "Travel - Vainilla & Coco (100g)",
                "sku": "VL-TRAVEL-VAINILLA",
                "price": "28000.00",
                "vip_price": "25000.00",  # Costo aprox: $9k (cera soja + lata dorada + esencia)
                "stock": 30,
                "min_order_quantity": 1,
                "max_order_quantity": 5,
            },
            {
                "name": "Travel - Sándalo & Madera (100g)",
                "sku": "VL-TRAVEL-SANDALO",
                "price": "28000.00",
                "vip_price": "25000.00",  # Costo aprox: $9k
                "stock": 25,
                "min_order_quantity": 1,
                "max_order_quantity": 5,
            },
            {
                "name": "Home - Jazmín (250g)",
                "sku": "VL-HOME-JAZMIN",
                "price": "75000.00",
                "vip_price": "67000.00",  # Costo aprox: $18k-22k (vaso vidrio + tapa madera)
                "stock": 20,
                "min_order_quantity": 1,
                "max_order_quantity": 3,
            },
            {
                "name": "Home - Vainilla & Coco (250g)",
                "sku": "VL-HOME-VAINILLA",
                "price": "72000.00",
                "vip_price": "65000.00",  # Costo aprox: $18k-22k
                "stock": 22,
                "min_order_quantity": 1,
                "max_order_quantity": 3,
            },
        ],
    },
    {
        "name": "Bruma de Almohada Deep Sleep",
        "category_key": "aromaterapia",
        "description": "El secreto para dormir como bebé. Fórmula botánica con lavanda francesa y manzanilla romana que calma el sistema nervioso y prepara tu mente para el descanso profundo. Spray fino que no mancha telas.",
        "preparation_days": 1,
        "is_active": True,
        "variants": [
            {
                "name": "Bruma Deep Sleep - 60ml",
                "sku": "BM-SLEEP-60",
                "price": "38000.00",
                "vip_price": "34000.00",  # Costo aprox: $10k (base líquida + esencia + botella spray)
                "stock": 35,
                "min_order_quantity": 1,
                "max_order_quantity": 4,
            },
        ],
    },
    # NOTA: Kit de Sahumerio Ritual fue removido por solicitud del cliente

    # ========================================================================
    # CATEGORÍA: SPA Y CUIDADO CORPORAL
    # ========================================================================
    {
        "name": "Aceite de Masaje Profesional",
        "category_key": "spa_care",
        "description": "La misma fórmula premium que usamos en cabina, ahora para tu hogar. Textura sedosa que se absorbe lentamente, ideal para masajes terapéuticos o hidratación post-ducha. Sin parabenos ni siliconas.",
        "preparation_days": 2,
        "is_active": True,
        "variants": [
            {
                "name": "Relax Total - Almendras & Lavanda (120ml)",
                "sku": "AM-RELAX-120",
                "price": "56000.00",
                "vip_price": "50000.00",  # Costo aprox: $14k-18k (aceite base calidad + botella pump)
                "stock": 25,
                "min_order_quantity": 1,
            },
            {
                "name": "Alivio Muscular - Árnica & Romero (120ml)",
                "sku": "AM-MUSCULAR-120",
                "price": "58000.00",
                "vip_price": "52000.00",  # Costo aprox: $14k-18k
                "stock": 20,
                "min_order_quantity": 1,
            },
        ],
    },
    {
        "name": "Sales de Baño Detox",
        "category_key": "spa_care",
        "description": "Sales minerales que transforman tu bañera en un spa terapéutico. La combinación de sal marina, Epsom y botánicos ayuda a desinflamar músculos, eliminar toxinas y relajar profundamente. Piel suave garantizada.",
        "preparation_days": 1,
        "is_active": True,
        "variants": [
            {
                "name": "Sales Detox - Lavanda & Eucalipto (250g)",
                "sku": "SB-DETOX-250",
                "price": "35000.00",
                "vip_price": "31000.00",  # Costo aprox: $8k (sales + hierbas + frasco vidrio)
                "stock": 30,
                "min_order_quantity": 1,
            },
        ],
    },

    # ========================================================================
    # CATEGORÍA: JOYERÍA ENERGÉTICA
    # ========================================================================
    {
        "name": "Pulsera Tejida Protección",
        "category_key": "joyeria",
        "description": "Más que joyería, un amuleto personal. Tejida a mano por artesanos caleños, combina la nobleza de la plata 925 con el poder vibracional de cuarzos naturales certificados. Cada piedra es única. Incluye tarjeta explicativa de propiedades energéticas.",
        "preparation_days": 3,
        "is_active": True,
        "variants": [
            {
                "name": "Protección - Ojo de Tigre & Plata 925",
                "sku": "PJ-PROT-OJOTIGRE",
                "price": "165000.00",
                "vip_price": "148000.00",  # Costo aprox: $50k-65k (materiales + mano obra + empaque lujo)
                "stock": 15,
                "min_order_quantity": 1,
            },
            {
                "name": "Protección - Turmalina Negra & Plata 925",
                "sku": "PJ-PROT-TURMALINA",
                "price": "175000.00",
                "vip_price": "157000.00",  # Costo aprox: $55k-70k
                "stock": 12,
                "min_order_quantity": 1,
            },
            {
                "name": "Protección - Onix & Plata 925",
                "sku": "PJ-PROT-ONIX",
                "price": "158000.00",
                "vip_price": "142000.00",  # Costo aprox: $45k-60k
                "stock": 18,
                "min_order_quantity": 1,
            },
        ],
    },
    {
        "name": "Pulsera Tejida Amor Propio",
        "category_key": "joyeria",
        "description": "Diseño exclusivo que celebra tu esencia. Oro laminado de 14k (gold filled) que no se oxida, combinado con cuarzos rosados que vibran en frecuencia del amor incondicional. Empaque premium en bolsa de terciopelo.",
        "preparation_days": 3,
        "is_active": True,
        "variants": [
            {
                "name": "Amor Propio - Cuarzo Rosa & Oro 14k",
                "sku": "PJ-AMOR-CUARZO",
                "price": "155000.00",
                "vip_price": "139000.00",  # Costo aprox: $45k-60k
                "stock": 20,
                "min_order_quantity": 1,
            },
            {
                "name": "Amor Propio - Rodocrosita & Oro 14k",
                "sku": "PJ-AMOR-RODOCROSITA",
                "price": "168000.00",
                "vip_price": "151000.00",  # Costo aprox: $50k-65k
                "stock": 15,
                "min_order_quantity": 1,
            },
        ],
    },
    {
        "name": "Pulsera Tejida Balance",
        "category_key": "joyeria",
        "description": "Equilibrio entre mente, cuerpo y espíritu. Diseño versátil con herrajes mixtos (plata y oro) que combina con todo. Cuarzos de alta frecuencia seleccionados por su claridad y energía. Regalo perfecto para quien busca armonía.",
        "preparation_days": 3,
        "is_active": True,
        "variants": [
            {
                "name": "Balance - Amatista & Herrajes Mixtos",
                "sku": "PJ-BAL-AMATISTA",
                "price": "148000.00",
                "vip_price": "133000.00",  # Costo aprox: $45k-60k
                "stock": 22,
                "min_order_quantity": 1,
            },
            {
                "name": "Balance - Aventurina Verde & Herrajes Mixtos",
                "sku": "PJ-BAL-AVENTURINA",
                "price": "142000.00",
                "vip_price": "128000.00",  # Costo aprox: $40k-55k
                "stock": 18,
                "min_order_quantity": 1,
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

    def _seed_product_categories(self):
        """
        Crea las categorías de productos. Se ejecuta FUERA de transaction.atomic()
        para evitar problemas de isolation level en Postgres.
        """
        PRODUCT_CATEGORIES = {
            "aromaterapia": {
                "name": "Aromaterapia y Ambientación",
                "description": "Aceites esenciales, velas, brumas y productos para crear ambientes de paz y bienestar en tu hogar.",
                "is_low_supervision": False,
            },
            "spa_care": {
                "name": "Spa y Cuidado Corporal",
                "description": "Aceites de masaje, sales, bombas de baño y productos profesionales para llevar la experiencia del spa a tu hogar.",
                "is_low_supervision": False,
            },
            "joyeria": {
                "name": "Joyería Energética",
                "description": "Pulseras tejidas artesanalmente con metales nobles y cuarzos naturales. Más que accesorios, amuletos con intención.",
                "is_low_supervision": False,
            },
        }

        from django.db import IntegrityError

        category_map = {}
        for key, cat_data in PRODUCT_CATEGORIES.items():
            try:
                category, _ = ServiceCategory.objects.get_or_create(
                    name=cat_data["name"],
                    defaults={
                        "description": cat_data["description"],
                        "is_low_supervision": cat_data["is_low_supervision"],
                    }
                )
            except IntegrityError:
                # Si hubo un problema de concurrencia, usar raw SQL para obtener la existente
                # Esto evita problemas de snapshot en transacciones concurrentes
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM spa_servicecategory WHERE name = %s",
                        [cat_data["name"]]
                    )
                    row = cursor.fetchone()
                    if row:
                        category = ServiceCategory.objects.get(id=row[0])
                    else:
                        raise RuntimeError(f"Categoría {cat_data['name']} no encontrada después de IntegrityError")

            # Actualizar siempre por si cambió algo
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
