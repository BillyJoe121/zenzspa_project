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
                "what_is_included": "• Masaje de espalda, cuello y hombros con técnicas de tejido profundo\n• Trabajo en piernas y pies con drenaje\n• Masaje de brazos y manos\n• Aceites esenciales de aromaterapia personalizados\n• Música relajante ambiental",
                "benefits": "• Libera tensiones musculares acumuladas\n• Mejora la circulación sanguínea y linfática\n• Reduce el estrés y la ansiedad\n• Aumenta la flexibilidad muscular\n• Promueve el sueño reparador",
                "contraindications": "• Fiebre o infecciones activas\n• Fracturas recientes o lesiones abiertas\n• Trombosis venosa profunda\n• Primer trimestre de embarazo\n• Quemaduras solares recientes",
            },
            {
                "name": "Terapéutico Focalizado",
                "description": "Tratamiento específico en zonas de mayor tensión como espalda, cuello y hombros, ideal para aliviar contracturas puntuales.",
                "duration": 50,
                "price": "130000.00",
                "vip_price": "117000.00",
                "what_is_included": "• Evaluación inicial de puntos de tensión\n• Masaje profundo en zona focalizada (espalda, cuello u hombros)\n• Técnicas de liberación miofascial\n• Aplicación de calor localizado si es necesario\n• Aceite terapéutico antiinflamatorio",
                "benefits": "• Alivio inmediato de contracturas\n• Reduce dolores de cabeza tensionales\n• Mejora la postura\n• Disminuye el dolor cervical\n• Aumenta el rango de movimiento",
                "contraindications": "• Hernias discales agudas\n• Inflamación severa en la zona\n• Lesiones musculares recientes (menos de 48h)\n• Osteoporosis avanzada\n• Anticoagulantes sin supervisión médica",
            },
            {
                "name": "Terapéutico Mixto",
                "description": "Equilibrio perfecto entre terapia profunda en zonas críticas y masaje relajante en el resto del cuerpo.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "130000.00",
                "what_is_included": "• Trabajo profundo en áreas de mayor tensión\n• Masaje relajante en zonas complementarias\n• Estiramientos pasivos suaves\n• Aceites esenciales premium\n• Técnica de piedras calientes en puntos clave",
                "benefits": "• Combina los beneficios terapéuticos y relajantes\n• Equilibrio entre alivio muscular y relajación mental\n• Mejora del estado de ánimo\n• Reducción del cortisol\n• Sensación de renovación completa",
                "contraindications": "• Condiciones cardíacas severas\n• Cáncer activo sin autorización médica\n• Infecciones en la piel\n• Estado de embriaguez\n• Fiebre alta",
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
                "what_is_included": "• Movimientos suaves y rítmicos siguiendo el sistema linfático\n• Trabajo en ganglios principales (cuello, axilas, inglés)\n• Técnica específica para reducir edemas\n• Aceite neutro hipoalergénico\n• Recomendaciones post-tratamiento",
                "benefits": "• Reduce la retención de líquidos\n• Mejora la circulación linfática\n• Fortalece el sistema inmunológico\n• Acelera la eliminación de toxinas\n• Reduce la celulitis y la piel de naranja",
                "contraindications": "• Infecciones agudas o fiebre\n• Insuficiencia cardíaca descompensada\n• Trombosis o flebitis\n• Hipotiroidismo no tratado\n• Cáncer sin autorización oncológica",
            },
            {
                "name": "Terapia de Equilibrio",
                "description": "Tratamiento holístico que combina drenaje linfático con puntos de acupresión para restaurar el balance energético del cuerpo.",
                "duration": 75,
                "price": "155000.00",
                "vip_price": "139000.00",
                "what_is_included": "• Drenaje linfático suave\n• Estimulación de puntos de acupresión\n• Trabajo en meridianos energéticos\n• Aceites esenciales equilibrantes\n• Momento de meditación guiada",
                "benefits": "• Restaura el equilibrio energético\n• Reduce el estrés emocional\n• Mejora la calidad del sueño\n• Armoniza cuerpo y mente\n• Aumenta la vitalidad general",
                "contraindications": "• Primer trimestre de embarazo\n• Marcapasos cardíaco\n• Epilepsia no controlada\n• Estados de ansiedad severa\n• Heridas abiertas en puntos de presión",
            },
            {
                "name": "Udvartana",
                "description": "Masaje ayurvédico con polvos herbales que exfolia, tonifica y estimula la circulación mientras elimina toxinas acumuladas en la piel.",
                "duration": 90,
                "price": "170000.00",
                "vip_price": "153000.00",
                "what_is_included": "• Exfoliación con polvos herbales ayurvédicos\n• Masaje vigoroso en dirección de los meridianos\n• Aceites herbales calientes\n• Envolvimiento detox (opcional)\n• Ducha para retirar polvos",
                "benefits": "• Exfolia y renueva la piel\n• Reduce la celulitis y grasa localizada\n• Tonifica los tejidos\n• Activa el metabolismo\n• Deja la piel suave y radiante",
                "contraindications": "• Piel muy sensible o con eczema activo\n• Quemaduras solares\n• Heridas abiertas\n• Alergia a hierbas (consultar ingredientes)\n• Embarazo",
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
                "what_is_included": "• Masaje relajante de cuerpo completo\n• Aromaterapia con aceites esenciales premium\n• Música terapéutica 432Hz\n• Ambiente con iluminación tenue\n• Té herbal de cortesía",
                "benefits": "• Relajación profunda del sistema nervioso\n• Reducción del estrés y ansiedad\n• Mejora el estado de ánimo\n• Promueve la claridad mental\n• Sensación de paz interior",
                "contraindications": "• Alergia a aceites esenciales (informar antes)\n• Claustrofobia severa\n• Condiciones que impidan estar recostado\n• Sensibilidad extrema a olores",
            },
            {
                "name": "Zen Extendido",
                "description": "Versión extendida de la Experiencia Zen con mayor tiempo dedicado a cada zona del cuerpo y técnicas de meditación guiada.",
                "duration": 90,
                "price": "165000.00",
                "vip_price": "148000.00",
                "what_is_included": "• Todo lo incluido en Experiencia Zen\n• 30 minutos adicionales de masaje\n• Meditación guiada al inicio\n• Técnica de respiración consciente\n• Mascarilla facial express",
                "benefits": "• Relajación más profunda y duradera\n• Conexión mente-cuerpo\n• Reset completo del sistema nervioso\n• Mejora la calidad del sueño durante días\n• Renovación de energía vital",
                "contraindications": "• Las mismas que Experiencia Zen\n• Dificultad para permanecer quieto por tiempo prolongado",
            },
            {
                "name": "Toque de Seda",
                "description": "Masaje delicado con aceites nutritivos que hidrata profundamente la piel mientras relaja el cuerpo con movimientos envolventes y sedosos.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "130000.00",
                "what_is_included": "• Masaje con técnica sueca suave\n• Aceites nutritivos de argán y jojoba\n• Movimientos largos y envolventes\n• Atención especial a zonas secas\n• Hidratación final intensiva",
                "benefits": "• Hidratación profunda de la piel\n• Nutrición de tejidos\n• Relajación muscular suave\n• Piel sedosa y luminosa\n• Mejora la elasticidad cutánea",
                "contraindications": "• Alergia a frutos secos (por aceites)\n• Acné severo en cuerpo\n• Piel con heridas abiertas",
            },
            {
                "name": "Herbal Essence",
                "description": "Tratamiento revitalizante con aceites esenciales herbales de notas masculinas, combinando masaje profundo y aromaterapia energizante.",
                "duration": 75,
                "price": "145000.00",
                "vip_price": "130000.00",
                "what_is_included": "• Masaje con presión media-profunda\n• Aceites de romero, menta y eucalipto\n• Técnicas energizantes\n• Trabajo en puntos de tensión\n• Toalla caliente en espalda",
                "benefits": "• Revitaliza el cuerpo y la mente\n• Alivia la fatiga muscular\n• Despeja las vías respiratorias\n• Aumenta el estado de alerta\n• Ideal después del ejercicio",
                "contraindications": "• Hipertensión no controlada\n• Sensibilidad al eucalipto o menta\n• Asma severa (consultar)\n• Migrañas activas",
            },
            {
                "name": "Cráneo Facial Ensueño",
                "description": "Masaje facial y craneal que libera tensiones acumuladas en rostro, cuero cabelludo y cuello, promoviendo relajación mental profunda.",
                "duration": 45,
                "price": "120000.00",
                "vip_price": "108000.00",
                "what_is_included": "• Masaje craneal con técnica india\n• Trabajo facial con aceites nutritivos\n• Masaje de cuello y hombros\n• Acupresión en puntos de tensión facial\n• Aceite capilar nutritivo",
                "benefits": "• Alivia dolores de cabeza\n• Reduce la tensión mandibular\n• Mejora la circulación facial\n• Promueve el crecimiento capilar\n• Relajación mental profunda",
                "contraindications": "• Sinusitis aguda\n• Migraña en curso\n• Conjuntivitis u otras infecciones oculares\n• Cirugía facial reciente",
            },
            {
                "name": "Cráneo Facial Ocaso",
                "description": "Ritual vespertino que combina técnicas de acupresión facial con masaje craneal para aliviar el estrés del día y preparar el descanso.",
                "duration": 50,
                "price": "130000.00",
                "vip_price": "117000.00",
                "what_is_included": "• Limpieza facial suave\n• Acupresión en puntos de medicina china\n• Masaje craneal relajante\n• Aceites esenciales de lavanda\n• Compresa tibia en ojos",
                "benefits": "• Prepara para el descanso nocturno\n• Alivia la fatiga visual\n• Reduce el bruxismo\n• Mejora la calidad del sueño\n• Suaviza líneas de expresión",
                "contraindications": "• Alergia a lavanda\n• Glaucoma\n• Desprendimiento de retina\n• Botox reciente (menos de 2 semanas)",
            },
            {
                "name": "Cráneo Facial Renacer",
                "description": "Tratamiento revitalizante que estimula puntos energéticos del rostro y cráneo para renovar la vitalidad y luminosidad de la piel.",
                "duration": 60,
                "price": "145000.00",
                "vip_price": "130000.00",
                "what_is_included": "• Exfoliación facial suave\n• Masaje lifting natural\n• Estimulación de puntos energéticos\n• Mascarilla revitalizante\n• Masaje craneal activador",
                "benefits": "• Efecto lifting natural inmediato\n• Luminosidad y frescura facial\n• Activa la circulación\n• Reduce la hinchazón matutina\n• Renueva la energía vital",
                "contraindications": "• Rosacea activa\n• Acné inflamatorio\n• Tratamientos estéticos recientes\n• Piel con heridas o irritación",
            },
            {
                "name": "Pediluvio",
                "description": "Baño terapéutico de pies con sales minerales y aceites esenciales, seguido de masaje reflexológico para activar puntos de bienestar.",
                "duration": 30,
                "price": "80000.00",
                "vip_price": "72000.00",
                "what_is_included": "• Baño de pies con sales minerales\n• Exfoliación de pies\n• Masaje reflexológico\n• Hidratación intensiva\n• Aceites esenciales relajantes",
                "benefits": "• Activa puntos reflejos de todo el cuerpo\n• Mejora la circulación de piernas\n• Reduce pies cansados e hinchados\n• Hidrata piel agrietada\n• Relajación a través de los pies",
                "contraindications": "• Pie diabético sin control\n• Hongos activos en pies\n• Heridas abiertas en pies\n• Varices severas",
            },
            {
                "name": "Limpieza Facial Sencilla",
                "description": "Protocolo básico de limpieza profunda que elimina impurezas, exfolia suavemente y equilibra la piel del rostro.",
                "duration": 45,
                "price": "110000.00",
                "vip_price": "99000.00",
                "what_is_included": "• Doble limpieza facial\n• Exfoliación enzimática suave\n• Extracción de impurezas (si aplica)\n• Mascarilla equilibrante\n• Hidratación según tipo de piel",
                "benefits": "• Piel limpia y luminosa\n• Poros desobstruidos\n• Textura más suave\n• Mejor absorción de productos\n• Rostro fresco y renovado",
                "contraindications": "• Herpes activo\n• Rosácea severa\n• Quemaduras solares\n• Tratamientos de Accutane en curso\n• Peeling químico reciente",
            },
            {
                "name": "Hidra Facial",
                "description": "Tratamiento facial avanzado con tecnología de hidrodermabrasión que limpia, exfolia e hidrata profundamente para una piel radiante.",
                "duration": 60,
                "price": "180000.00",
                "vip_price": "162000.00",
                "what_is_included": "• Limpieza profunda con tecnología\n• Hidrodermabrasión profesional\n• Extracción indolora de impurezas\n• Infusión de serums según necesidad\n• Mascarilla LED (opcional)\n• Protección solar final",
                "benefits": "• Limpieza profunda sin irritación\n• Hidratación inigualable\n• Resultados visibles inmediatos\n• Reduce líneas finas\n• Piel radiante y juvenil",
                "contraindications": "• Embarazo (algunas tecnologías)\n• Marca pasos\n• Rosácea activa\n• Herpes labial\n• Alergias severas a productos faciales",
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
        "what_is_included": "• Frasco de vidrio ámbar de 10ml con gotero\n• Aceite esencial 100% puro sin diluir\n• Etiqueta con información de origen y propiedades\n• Caja de cartón reciclado con instrucciones",
        "benefits": "• Aromaterapia natural que mejora el estado de ánimo\n• Propiedades relajantes o energizantes según variedad\n• Purifica el ambiente del hogar\n• Ayuda a conciliar el sueño\n• Reduce el estrés y la ansiedad",
        "how_to_use": "1. Difusor: Agregar 3-5 gotas en difusor con agua\n2. Masaje: Diluir 2-3 gotas en 10ml de aceite portador\n3. Baño: Añadir 5-8 gotas al agua tibia de la tina\n4. Inhalación: 1-2 gotas en pañuelo o manos\n\n⚠️ No aplicar directamente sobre la piel sin diluir",
        "variants": [
            {
                "name": "Lavanda del Valle - 10ml",
                "sku": "AE-LAVANDA-10",
                "price": "42000.00",
                "vip_price": "37000.00",
                "stock": 40,
                "min_order_quantity": 1,
            },
            {
                "name": "Eucalipto & Menta - 10ml",
                "sku": "AE-EUCALIPTO-10",
                "price": "42000.00",
                "vip_price": "37000.00",
                "stock": 35,
                "min_order_quantity": 1,
            },
            {
                "name": "Naranja Dulce - 10ml",
                "sku": "AE-NARANJA-10",
                "price": "39000.00",
                "vip_price": "35000.00",
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
        "what_is_included": "• Vela de cera de soja 100% natural\n• Mecha de algodón libre de plomo\n• Envase reutilizable (lata o vidrio según variante)\n• Fragancia premium de larga duración\n• Instrucciones de uso y seguridad",
        "benefits": "• Aromatiza espacios de forma natural\n• No produce hollín negro como las velas de parafina\n• Crea ambiente de relajación y bienestar\n• Ideal para meditación y rituales de autocuidado\n• El envase es reutilizable después de terminar",
        "how_to_use": "1. Primer uso: Dejar encendida hasta que toda la superficie se derrita (2-3h)\n2. Recortar la mecha a 5mm antes de cada uso\n3. Máximo 4 horas continuas de uso\n4. Usar en superficie plana y estable\n5. Mantener alejada de corrientes de aire\n\n💡 Tip: Para mayor duración, apagar soplando suavemente",
        "variants": [
            {
                "name": "Travel - Vainilla & Coco (100g)",
                "sku": "VL-TRAVEL-VAINILLA",
                "price": "28000.00",
                "vip_price": "25000.00",
                "stock": 30,
                "min_order_quantity": 1,
                "max_order_quantity": 5,
            },
            {
                "name": "Travel - Sándalo & Madera (100g)",
                "sku": "VL-TRAVEL-SANDALO",
                "price": "28000.00",
                "vip_price": "25000.00",
                "stock": 25,
                "min_order_quantity": 1,
                "max_order_quantity": 5,
            },
            {
                "name": "Home - Jazmín (250g)",
                "sku": "VL-HOME-JAZMIN",
                "price": "75000.00",
                "vip_price": "67000.00",
                "stock": 20,
                "min_order_quantity": 1,
                "max_order_quantity": 3,
            },
            {
                "name": "Home - Vainilla & Coco (250g)",
                "sku": "VL-HOME-VAINILLA",
                "price": "72000.00",
                "vip_price": "65000.00",
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
        "what_is_included": "• Botella de vidrio con atomizador fino de 60ml\n• Fórmula con aceites esenciales de lavanda y manzanilla\n• Base de agua destilada y alcohol vegetal\n• Empaque en caja kraft con instrucciones",
        "benefits": "• Promueve el sueño profundo y reparador\n• Calma la mente antes de dormir\n• Reduce el tiempo para conciliar el sueño\n• Aroma relajante que persiste toda la noche\n• No mancha sábanas ni almohadas",
        "how_to_use": "1. Agitar bien antes de usar\n2. Rociar 2-3 veces sobre la almohada a 30cm de distancia\n3. Aplicar 10-15 minutos antes de acostarse\n4. También puede usarse en sábanas y ropa de cama\n5. Opcional: rociar en muñecas y sienes\n\n🌙 Ritual nocturno: Combinar con respiración profunda",
        "variants": [
            {
                "name": "Bruma Deep Sleep - 60ml",
                "sku": "BM-SLEEP-60",
                "price": "38000.00",
                "vip_price": "34000.00",
                "stock": 35,
                "min_order_quantity": 1,
                "max_order_quantity": 4,
            },
        ],
    },

    # ========================================================================
    # CATEGORÍA: SPA Y CUIDADO CORPORAL
    # ========================================================================
    {
        "name": "Aceite de Masaje Profesional",
        "category_key": "spa_care",
        "description": "La misma fórmula premium que usamos en cabina, ahora para tu hogar. Textura sedosa que se absorbe lentamente, ideal para masajes terapéuticos o hidratación post-ducha. Sin parabenos ni siliconas.",
        "preparation_days": 2,
        "is_active": True,
        "what_is_included": "• Botella de 120ml con dosificador pump\n• Aceite base de almendras dulces y jojoba\n• Aceites esenciales según variante\n• Vitamina E natural como antioxidante\n• Libre de parabenos, siliconas y colorantes",
        "benefits": "• Deslizamiento perfecto para masajes profesionales\n• Hidratación profunda que no deja sensación grasosa\n• Nutre y suaviza la piel seca\n• Aromaterapia durante el masaje\n• Absorción gradual para mejor trabajabilidad",
        "how_to_use": "1. MASAJE: Calentar entre las manos y aplicar con movimientos largos\n2. POST-DUCHA: Aplicar sobre piel húmeda para mejor absorción\n3. Usar 1-2 pumps por zona del cuerpo\n4. Masajear hasta absorción completa\n5. Evitar contacto con ojos y mucosas\n\n💆 Tip: Tibiar la botella en agua caliente antes del masaje",
        "variants": [
            {
                "name": "Relax Total - Almendras & Lavanda (120ml)",
                "sku": "AM-RELAX-120",
                "price": "56000.00",
                "vip_price": "50000.00",
                "stock": 25,
                "min_order_quantity": 1,
            },
            {
                "name": "Alivio Muscular - Árnica & Romero (120ml)",
                "sku": "AM-MUSCULAR-120",
                "price": "58000.00",
                "vip_price": "52000.00",
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
        "what_is_included": "• Frasco de vidrio de 250g con tapa hermética\n• Mezcla de sal marina y sal de Epsom\n• Hierbas secas naturales (lavanda y eucalipto)\n• Aceites esenciales puros\n• Cuchara medidora de madera incluida",
        "benefits": "• Desintoxica y purifica la piel\n• Relaja músculos tensos y adoloridos\n• Reduce la inflamación y la retención de líquidos\n• El magnesio de Epsom calma el sistema nervioso\n• Deja la piel increíblemente suave",
        "how_to_use": "1. Llenar la tina con agua tibia (37-40°C)\n2. Agregar 2-3 cucharadas de sales mientras corre el agua\n3. Mezclar con la mano para disolver\n4. Sumergirse por 15-20 minutos\n5. Enjuagar con agua limpia al salir\n\n🛁 Ritual: Encender velas y música relajante para potenciar efectos",
        "variants": [
            {
                "name": "Sales Detox - Lavanda & Eucalipto (250g)",
                "sku": "SB-DETOX-250",
                "price": "35000.00",
                "vip_price": "31000.00",
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
        "what_is_included": "• Pulsera tejida a mano con nudo ajustable\n• Piedras naturales certificadas\n• Herrajes de plata 925 con sello de garantía\n• Bolsa de terciopelo para almacenamiento\n• Tarjeta con propiedades de las piedras\n• Certificado de autenticidad",
        "benefits": "• Protección energética contra energías negativas\n• Fortalece el campo áurico personal\n• Aumenta la confianza y la seguridad\n• Piedras cargadas con intención positiva\n• Diseño versátil para uso diario",
        "how_to_use": "1. ACTIVACIÓN: Al recibirla, sostenla entre tus manos y visualiza tu intención\n2. Usar en la muñeca izquierda para recibir energía protectora\n3. Usar en la muñeca derecha para proyectar fuerza\n4. Limpiar energéticamente cada luna llena con humo de incienso\n5. No mojar (retirar antes de ducha o piscina)\n\n✨ Tip: Cargar bajo la luz de la luna una noche al mes",
        "variants": [
            {
                "name": "Protección - Ojo de Tigre & Plata 925",
                "sku": "PJ-PROT-OJOTIGRE",
                "price": "165000.00",
                "vip_price": "148000.00",
                "stock": 15,
                "min_order_quantity": 1,
            },
            {
                "name": "Protección - Turmalina Negra & Plata 925",
                "sku": "PJ-PROT-TURMALINA",
                "price": "175000.00",
                "vip_price": "157000.00",
                "stock": 12,
                "min_order_quantity": 1,
            },
            {
                "name": "Protección - Onix & Plata 925",
                "sku": "PJ-PROT-ONIX",
                "price": "158000.00",
                "vip_price": "142000.00",
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
        "what_is_included": "• Pulsera tejida a mano con cierre ajustable\n• Piedras naturales de cuarzo rosa o rodocrosita\n• Herrajes de oro laminado 14k (gold filled)\n• Bolsa de terciopelo premium\n• Tarjeta con afirmaciones de amor propio\n• Certificado de autenticidad de piedras",
        "benefits": "• Vibra en la frecuencia del amor incondicional\n• Ayuda a sanar heridas emocionales\n• Aumenta la autoestima y la confianza\n• Atrae relaciones armoniosas\n• Conecta con la energía del corazón",
        "how_to_use": "1. RITUAL DE CONEXIÓN: Coloca sobre tu corazón y respira profundo 3 veces\n2. Usar en la muñeca izquierda para abrir el chakra del corazón\n3. Repetir la afirmación: 'Me amo y me acepto completamente'\n4. Limpiar con agua de rosas cada semana\n5. No exponer al cloro o agua salada\n\n💕 Ideal como regalo para alguien especial o para ti misma",
        "variants": [
            {
                "name": "Amor Propio - Cuarzo Rosa & Oro 14k",
                "sku": "PJ-AMOR-CUARZO",
                "price": "155000.00",
                "vip_price": "139000.00",
                "stock": 20,
                "min_order_quantity": 1,
            },
            {
                "name": "Amor Propio - Rodocrosita & Oro 14k",
                "sku": "PJ-AMOR-RODOCROSITA",
                "price": "168000.00",
                "vip_price": "151000.00",
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
        "what_is_included": "• Pulsera tejida artesanalmente\n• Piedras de amatista o aventurina natural\n• Herrajes mixtos plata 925 y oro laminado 14k\n• Bolsa de terciopelo para guardar\n• Tarjeta con guía de meditación\n• Certificado de autenticidad",
        "benefits": "• Armoniza los chakras principales\n• Equilibra las emociones y la mente\n• Atrae abundancia y prosperidad (aventurina)\n• Promueve la paz interior (amatista)\n• Diseño versátil para cualquier ocasión",
        "how_to_use": "1. MEDITACIÓN: Sostener la pulsera mientras meditas para amplificar la conexión\n2. Usar en cualquier muñeca según tu intuición del día\n3. En momentos de estrés, tocar las piedras y respirar profundo\n4. Limpiar pasándola por humo de palo santo\n5. Guardar en bolsa de terciopelo cuando no se use\n\n☯️ Mantras sugeridos: 'Estoy en equilibrio' o 'Fluyo con la vida'",
        "variants": [
            {
                "name": "Balance - Amatista & Herrajes Mixtos",
                "sku": "PJ-BAL-AMATISTA",
                "price": "148000.00",
                "vip_price": "133000.00",
                "stock": 22,
                "min_order_quantity": 1,
            },
            {
                "name": "Balance - Aventurina Verde & Herrajes Mixtos",
                "sku": "PJ-BAL-AVENTURINA",
                "price": "142000.00",
                "vip_price": "128000.00",
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
            
            # Buscar categoría incluso si está eliminada
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
                
                # Buscar servicio incluso si está eliminado
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

        category_map = {}
        for key, cat_data in PRODUCT_CATEGORIES.items():
            # Buscar categoría incluso si está eliminada
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
                
                # Actualizar campos si cambiaron
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
