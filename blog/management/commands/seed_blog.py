from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from blog.models import Category, Tag, Article
import random


class Command(BaseCommand):
    help = 'Pobla el blog con datos de prueba para desarrollo'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Creando datos de prueba para el blog...'))

        # Crear categorías
        categories_data = [
            {
                'name': 'Ayurveda',
                'description': 'Artículos sobre medicina ayurvédica y sus beneficios'
            },
            {
                'name': 'Spa y Tratamientos',
                'description': 'Guías sobre tratamientos de spa y cuidados estéticos'
            },
            {
                'name': 'Bienestar',
                'description': 'Consejos para el bienestar físico y mental'
            },
            {
                'name': 'Nutrición',
                'description': 'Alimentación saludable y dietas ayurvédicas'
            },
            {
                'name': 'Yoga y Meditación',
                'description': 'Prácticas de yoga y meditación para el equilibrio'
            },
        ]

        categories = []
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )
            categories.append(category)
            if created:
                self.stdout.write(self.style.SUCCESS(f'✓ Categoría creada: {category.name}'))

        # Crear etiquetas
        tags_data = [
            'Vata', 'Pitta', 'Kapha', 'Doshas', 'Masajes',
            'Relajación', 'Detox', 'Salud', 'Mindfulness', 'Autocuidado'
        ]

        tags = []
        for tag_name in tags_data:
            tag, created = Tag.objects.get_or_create(name=tag_name)
            tags.append(tag)
            if created:
                self.stdout.write(self.style.SUCCESS(f'✓ Etiqueta creada: {tag.name}'))

        # Crear artículos de ejemplo
        articles_data = [
            {
                'title': '¿Qué es Ayurveda y cómo puede mejorar tu vida?',
                'subtitle': 'Descubre los fundamentos de la medicina tradicional india',
                'content': '''
El Ayurveda es un sistema de medicina tradicional originario de la India que tiene más de 5,000 años de antigüedad.
La palabra "Ayurveda" proviene del sánscrito y significa "ciencia de la vida".

Este antiguo sistema de curación se basa en la creencia de que la salud y el bienestar dependen de un delicado
equilibrio entre la mente, el cuerpo y el espíritu. Su objetivo principal no es solo combatir enfermedades,
sino promover la buena salud en general.

Los tres doshas (Vata, Pitta y Kapha) son los pilares fundamentales del Ayurveda. Cada persona tiene una
combinación única de estos doshas que determina sus características físicas, mentales y emocionales.

En StudioZens, ofrecemos tratamientos ayurvédicos personalizados según tu constitución única (Prakriti)
para ayudarte a alcanzar el equilibrio y bienestar óptimo.
                ''',
                'category': 'Ayurveda',
                'tags': ['Doshas', 'Salud', 'Vata', 'Pitta', 'Kapha'],
                'is_featured': True,
                'featured_order': 1,
            },
            {
                'title': 'Los Beneficios del Masaje Abhyanga',
                'subtitle': 'El masaje ayurvédico con aceite que nutre cuerpo y alma',
                'content': '''
El Abhyanga es uno de los tratamientos más importantes en el Ayurveda. Este masaje con aceites herbales calientes
no solo relaja el cuerpo, sino que también equilibra los doshas y promueve la longevidad.

Beneficios principales:
- Nutre y fortalece los tejidos corporales
- Mejora la circulación sanguínea y linfática
- Calma el sistema nervioso
- Promueve un sueño profundo y reparador
- Aumenta la flexibilidad de las articulaciones
- Elimina toxinas del cuerpo
- Rejuvenece la piel

En nuestro spa, utilizamos aceites específicos según tu constitución ayurvédica para maximizar los beneficios
de este antiguo tratamiento.
                ''',
                'category': 'Spa y Tratamientos',
                'tags': ['Masajes', 'Relajación', 'Ayurveda', 'Autocuidado'],
                'is_featured': True,
                'featured_order': 2,
            },
            {
                'title': 'Descubre tu Dosha: Guía Completa',
                'subtitle': 'Aprende a identificar tu constitución ayurvédica',
                'content': '''
En Ayurveda, los doshas son las tres energías fundamentales que gobiernan nuestro cuerpo y mente.
Comprender tu dosha dominante es el primer paso para lograr el equilibrio.

VATA (Aire y Éter):
Características: Creativo, energético, delgado, piel seca
Desequilibrios: Ansiedad, insomnio, estreñimiento

PITTA (Fuego y Agua):
Características: Inteligente, decidido, complexión media, piel sensible
Desequilibrios: Irritabilidad, acidez, inflamaciones

KAPHA (Tierra y Agua):
Características: Calmado, fuerte, constitución robusta, piel grasa
Desequilibrios: Letargo, aumento de peso, congestión

Realiza nuestro test de doshas en StudioZens para descubrir tu constitución única y recibir
recomendaciones personalizadas.
                ''',
                'category': 'Ayurveda',
                'tags': ['Doshas', 'Vata', 'Pitta', 'Kapha', 'Autocuidado'],
                'is_featured': False,
            },
            {
                'title': 'Alimentación Ayurvédica para el Equilibrio',
                'subtitle': 'Cómo comer según tu dosha',
                'content': '''
La nutrición es uno de los pilares fundamentales del Ayurveda. Según este sistema, no existe una dieta
universal, sino que cada persona debe comer según su constitución única.

Para VATA: Alimentos calientes, cocidos, nutritivos. Sabores dulce, salado, ácido.
Para PITTA: Alimentos frescos, crudos, moderados. Sabores dulce, amargo, astringente.
Para KAPHA: Alimentos ligeros, calientes, especiados. Sabores picante, amargo, astringente.

Principios generales:
- Come en un ambiente tranquilo
- Mastica bien los alimentos
- Evita comer cuando estés estresado
- Respeta las señales de hambre y saciedad
- Prefiere alimentos frescos y de temporada

Consulta con nuestros especialistas en StudioZens para un plan nutricional personalizado.
                ''',
                'category': 'Nutrición',
                'tags': ['Nutrición', 'Doshas', 'Salud', 'Ayurveda'],
                'is_featured': True,
                'featured_order': 3,
            },
            {
                'title': 'Meditación para Principiantes',
                'subtitle': 'Tu camino hacia la paz interior',
                'content': '''
La meditación es una práctica milenaria que nos ayuda a calmar la mente, reducir el estrés y
conectar con nuestro ser interior.

Pasos para comenzar:
1. Encuentra un lugar tranquilo
2. Siéntate cómodamente con la espalda recta
3. Cierra los ojos suavemente
4. Enfócate en tu respiración
5. Cuando la mente divague, regresa gentilmente a la respiración

Beneficios de la meditación regular:
- Reduce el estrés y la ansiedad
- Mejora la concentración
- Aumenta la autoconciencia
- Promueve el bienestar emocional
- Mejora la calidad del sueño

En StudioZens ofrecemos sesiones guiadas de meditación para todos los niveles.
                ''',
                'category': 'Yoga y Meditación',
                'tags': ['Meditación', 'Mindfulness', 'Relajación', 'Bienestar'],
                'is_featured': False,
            },
            {
                'title': 'Desintoxicación Ayurvédica: Panchakarma',
                'subtitle': 'El proceso de purificación profunda del cuerpo',
                'content': '''
Panchakarma es el sistema de desintoxicación más completo del Ayurveda. Este tratamiento elimina
toxinas profundamente arraigadas y restablece el equilibrio natural del cuerpo.

Las cinco acciones principales:
1. Vamana (Vómito terapéutico)
2. Virechana (Purgación)
3. Basti (Enemas herbales)
4. Nasya (Limpieza nasal)
5. Raktamokshana (Purificación sanguínea)

Beneficios:
- Eliminación profunda de toxinas
- Rejuvenecimiento celular
- Fortalecimiento del sistema inmune
- Mejora de la digestión
- Aumento de energía y vitalidad

Importante: Panchakarma debe realizarse bajo supervisión de profesionales capacitados.
Consulta nuestros programas en StudioZens.
                ''',
                'category': 'Spa y Tratamientos',
                'tags': ['Detox', 'Ayurveda', 'Salud', 'Tratamientos'],
                'is_featured': False,
            },
        ]

        # Crear artículos
        for i, art_data in enumerate(articles_data):
            # Buscar categoría y etiquetas
            category = Category.objects.get(name=art_data['category'])
            article_tags = [Tag.objects.get_or_create(name=tag_name)[0] for tag_name in art_data['tags']]

            # Crear artículo publicado hace X días
            days_ago = len(articles_data) - i
            published_date = timezone.now() - timedelta(days=days_ago)

            article, created = Article.objects.get_or_create(
                title=art_data['title'],
                defaults={
                    'subtitle': art_data['subtitle'],
                    'content': art_data['content'].strip(),
                    'category': category,
                    'status': 'published',
                    'published_at': published_date,
                    'is_featured': art_data.get('is_featured', False),
                    'featured_order': art_data.get('featured_order', 0),
                    'author_name': 'Equipo StudioZens',
                    'views_count': random.randint(50, 500),
                }
            )

            if created:
                article.tags.set(article_tags)
                self.stdout.write(self.style.SUCCESS(f'✓ Artículo creado: {article.title}'))

        # Crear algunos borradores
        draft_article, created = Article.objects.get_or_create(
            title='[BORRADOR] Próximamente: Nuevos tratamientos de invierno',
            defaults={
                'subtitle': 'Artículo en desarrollo',
                'content': 'Contenido por definir...',
                'status': 'draft',
                'author_name': 'Editor',
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Borrador creado: {draft_article.title}'))

        self.stdout.write(self.style.SUCCESS('\n✅ Blog poblado exitosamente!'))
        self.stdout.write(self.style.WARNING('\nPuedes acceder al blog en:'))
        self.stdout.write('  - Admin: http://localhost:8000/admin/blog/')
        self.stdout.write('  - API: http://localhost:8000/api/v1/blog/articles/')
