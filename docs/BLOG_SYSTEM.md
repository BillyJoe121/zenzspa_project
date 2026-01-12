# Sistema de Blog - StudioZens

## Descripción General

Sistema completo de gestión de blog para StudioZens con soporte para artículos, categorías, etiquetas e imágenes. Incluye API REST completa y panel de administración Django.

## Características

### ✅ Modelos Implementados

1. **Article** - Artículos del blog
   - Título, subtítulo, extracto, contenido
   - Imagen de portada con texto alternativo
   - Estados: borrador, publicado, archivado
   - Categoría y etiquetas múltiples
   - Autor (usuario del sistema o nombre custom)
   - SEO: meta título y descripción
   - Métricas: vistas, tiempo de lectura
   - Sistema de destacados con orden
   - Auditoría con simple-history
   - Auto-generación de slug único
   - Auto-cálculo de tiempo de lectura

2. **Category** - Categorías del blog
   - Nombre, slug, descripción
   - Relación uno a muchos con artículos

3. **Tag** - Etiquetas para clasificación
   - Nombre, slug
   - Relación muchos a muchos con artículos

4. **ArticleImage** - Galería de imágenes por artículo
   - Imagen con texto alternativo y caption
   - Sistema de ordenamiento
   - Relación muchos a uno con artículos

### 🔌 API REST Endpoints

#### Artículos

**Públicos (sin autenticación):**
```
GET    /api/v1/blog/articles/              - Lista artículos publicados
GET    /api/v1/blog/articles/{slug}/       - Detalle de artículo (incrementa vistas)
GET    /api/v1/blog/articles/featured/     - Artículos destacados
GET    /api/v1/blog/articles/recent/       - Últimos 10 artículos
GET    /api/v1/blog/articles/popular/      - Más vistos
```

**Admin (requiere autenticación + staff):**
```
POST   /api/v1/blog/articles/              - Crear artículo
PUT    /api/v1/blog/articles/{slug}/       - Actualizar artículo completo
PATCH  /api/v1/blog/articles/{slug}/       - Actualizar parcial
DELETE /api/v1/blog/articles/{slug}/       - Eliminar artículo
POST   /api/v1/blog/articles/{slug}/publish/    - Publicar
POST   /api/v1/blog/articles/{slug}/unpublish/  - Despublicar
GET    /api/v1/blog/articles/{slug}/images/     - Listar imágenes
POST   /api/v1/blog/articles/{slug}/images/     - Agregar imagen
```

**Filtros disponibles:**
```
?category=ayurveda              - Filtrar por categoría (slug)
?tags__slug=doshas              - Filtrar por etiqueta (slug)
?status=published               - Filtrar por estado (solo admin)
?is_featured=true               - Solo destacados
?search=meditacion              - Buscar en título, subtítulo, contenido
?ordering=-published_at         - Ordenar por fecha publicación desc
?ordering=views_count           - Ordenar por vistas asc
```

#### Categorías

```
GET    /api/v1/blog/categories/            - Lista todas
GET    /api/v1/blog/categories/{slug}/     - Detalle
POST   /api/v1/blog/categories/            - Crear (admin)
PUT    /api/v1/blog/categories/{slug}/     - Actualizar (admin)
DELETE /api/v1/blog/categories/{slug}/     - Eliminar (admin)
```

#### Etiquetas

```
GET    /api/v1/blog/tags/                  - Lista todas
GET    /api/v1/blog/tags/{slug}/           - Detalle
POST   /api/v1/blog/tags/                  - Crear (admin)
PUT    /api/v1/blog/tags/{slug}/           - Actualizar (admin)
DELETE /api/v1/blog/tags/{slug}/           - Eliminar (admin)
```

#### Imágenes

```
GET    /api/v1/blog/images/                - Lista todas (admin)
GET    /api/v1/blog/images/?article_id=1   - Filtrar por artículo
POST   /api/v1/blog/images/                - Subir imagen (admin)
DELETE /api/v1/blog/images/{id}/           - Eliminar imagen (admin)
```

### 📊 Panel de Administración Django

Acceso: `http://localhost:8000/admin/blog/`

**Funcionalidades:**

1. **Artículos**
   - Lista con filtros por estado, categoría, etiquetas, fechas
   - Badge visual de estado (publicado/borrador/archivado)
   - Búsqueda en título, subtítulo, contenido
   - Preview de imagen de portada
   - Inline para agregar múltiples imágenes
   - Campos agrupados en secciones colapsables
   - Auto-completado de slug
   - Selección múltiple de tags
   - Historial de cambios (simple-history)

   **Acciones masivas:**
   - Publicar artículos seleccionados
   - Cambiar a borrador
   - Marcar/desmarcar como destacados

2. **Categorías**
   - Lista simple con contador de artículos
   - Auto-generación de slug

3. **Etiquetas**
   - Lista simple con contador de artículos
   - Auto-generación de slug

4. **Imágenes**
   - Preview de imagen
   - Filtros por artículo y fecha
   - Ordenamiento manual

### 🔐 Permisos y Seguridad

- **Lectura**: Pública para artículos publicados
- **Escritura**: Solo usuarios autenticados con `is_staff=True`
- **Boradores**: Solo visibles para administradores
- **Throttling**: Heredado de configuración global DRF

### 📁 Estructura de Archivos

```
blog/
├── migrations/
│   └── 0001_initial.py
├── management/
│   └── commands/
│       └── seed_blog.py          # Comando para poblar datos de prueba
├── __init__.py
├── admin.py                       # Configuración del admin
├── apps.py
├── models.py                      # Article, Category, Tag, ArticleImage
├── permissions.py                 # IsAdminOrReadOnly
├── serializers.py                 # Serializers para API
├── urls.py                        # Rutas del módulo
└── views.py                       # ViewSets
```

### 🗄️ Base de Datos

**Tablas creadas:**
- `blog_article` - Artículos principales
- `blog_article_tags` - Relación muchos a muchos
- `blog_category` - Categorías
- `blog_tag` - Etiquetas
- `blog_articleimage` - Imágenes adicionales
- `blog_historicalarticle` - Auditoría de cambios

**Índices optimizados:**
- `(published_at DESC, status)` - Para listados
- `(slug)` - Para búsqueda por slug
- `(is_featured, featured_order DESC)` - Para destacados

### 📸 Manejo de Imágenes

**Portadas:**
- Campo: `cover_image`
- Ruta: `media/blog/covers/YYYY/MM/`
- Texto alt: `cover_image_alt`

**Galería:**
- Campo: `image`
- Ruta: `media/blog/content/YYYY/MM/`
- Texto alt: `alt_text`
- Caption: `caption`
- Ordenamiento: `order`

**Requisito:** Pillow instalado (ya incluido)

### 🚀 Uso Rápido

#### 1. Poblar con datos de prueba

```bash
python manage.py seed_blog
```

Esto creará:
- 5 categorías (Ayurveda, Spa y Tratamientos, Bienestar, Nutrición, Yoga y Meditación)
- 10 etiquetas
- 6 artículos publicados con contenido real
- 1 borrador

#### 2. Crear artículo desde el admin

1. Ir a http://localhost:8000/admin/blog/article/add/
2. Completar título (el slug se genera automático)
3. Agregar contenido
4. Subir imagen de portada (opcional)
5. Seleccionar categoría y tags
6. Elegir estado: "Borrador" para guardar sin publicar
7. Guardar

#### 3. Publicar artículo

**Opción A - Desde el admin:**
1. Cambiar estado a "Publicado"
2. Establecer fecha de publicación
3. Guardar

**Opción B - Desde acción masiva:**
1. Seleccionar artículos
2. Acción: "Publicar artículos seleccionados"

**Opción C - Desde API:**
```bash
POST /api/v1/blog/articles/{slug}/publish/
```

#### 4. Consultar artículos desde frontend

**Listar todos los publicados:**
```javascript
fetch('http://localhost:8000/api/v1/blog/articles/')
  .then(res => res.json())
  .then(data => console.log(data))
```

**Artículos destacados:**
```javascript
fetch('http://localhost:8000/api/v1/blog/articles/featured/')
  .then(res => res.json())
  .then(data => console.log(data))
```

**Detalle de artículo:**
```javascript
fetch('http://localhost:8000/api/v1/blog/articles/que-es-ayurveda-y-como-puede-mejorar-tu-vida/')
  .then(res => res.json())
  .then(data => console.log(data))
```

**Filtrar por categoría:**
```javascript
fetch('http://localhost:8000/api/v1/blog/articles/?category__slug=ayurveda')
  .then(res => res.json())
  .then(data => console.log(data))
```

### 📝 Ejemplo de Respuesta API

**GET /api/v1/blog/articles/**

```json
{
  "count": 6,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "¿Qué es Ayurveda y cómo puede mejorar tu vida?",
      "slug": "que-es-ayurveda-y-como-puede-mejorar-tu-vida",
      "subtitle": "Descubre los fundamentos de la medicina tradicional india",
      "excerpt": "El Ayurveda es un sistema de medicina tradicional originario de la India...",
      "cover_image_url": "http://localhost:8000/media/blog/covers/2024/12/ayurveda.jpg",
      "cover_image_alt": "Medicina ayurvédica",
      "category_name": "Ayurveda",
      "category_slug": "ayurveda",
      "tags": [
        {
          "id": 4,
          "name": "Doshas",
          "slug": "doshas",
          "articles_count": 3
        },
        {
          "id": 8,
          "name": "Salud",
          "slug": "salud",
          "articles_count": 4
        }
      ],
      "author_display": "Equipo StudioZens",
      "status": "published",
      "is_published": true,
      "published_at": "2024-12-07T10:30:00Z",
      "views_count": 234,
      "reading_time_minutes": 5,
      "is_featured": true,
      "created_at": "2024-12-07T10:00:00Z",
      "updated_at": "2024-12-07T10:30:00Z"
    }
  ]
}
```

### 🎨 Integración con Frontend

#### Página de listado de blog

```jsx
// Componente ejemplo en React
function BlogList() {
  const [articles, setArticles] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/blog/articles/')
      .then(res => res.json())
      .then(data => setArticles(data.results));
  }, []);

  return (
    <div className="blog-grid">
      {articles.map(article => (
        <article key={article.id}>
          <img src={article.cover_image_url} alt={article.cover_image_alt} />
          <h2>{article.title}</h2>
          <p>{article.subtitle}</p>
          <span>{article.reading_time_minutes} min lectura</span>
          <Link to={`/blog/${article.slug}`}>Leer más</Link>
        </article>
      ))}
    </div>
  );
}
```

#### Página de detalle

```jsx
function BlogDetail({ slug }) {
  const [article, setArticle] = useState(null);

  useEffect(() => {
    fetch(`http://localhost:8000/api/v1/blog/articles/${slug}/`)
      .then(res => res.json())
      .then(data => setArticle(data));
  }, [slug]);

  if (!article) return <div>Cargando...</div>;

  return (
    <article>
      <img src={article.cover_image_url} alt={article.cover_image_alt} />
      <h1>{article.title}</h1>
      <p className="subtitle">{article.subtitle}</p>
      <div className="meta">
        <span>Por {article.author_display}</span>
        <span>{new Date(article.published_at).toLocaleDateString()}</span>
        <span>{article.views_count} vistas</span>
      </div>
      <div className="content" dangerouslySetInnerHTML={{ __html: article.content }} />
      <div className="tags">
        {article.tags.map(tag => (
          <span key={tag.id}>{tag.name}</span>
        ))}
      </div>
    </article>
  );
}
```

### 🔧 Configuración Adicional

#### Variables de entorno (opcional)

No requiere variables adicionales. Usa la configuración existente de:
- `MEDIA_ROOT` - Para almacenamiento de imágenes
- `MEDIA_URL` - Para URLs de imágenes
- DRF settings - Para paginación y permisos

#### Consideraciones de producción

1. **Almacenamiento de imágenes:**
   - Configurar S3 o similar para `MEDIA_ROOT`
   - Implementar CDN para servir imágenes

2. **Performance:**
   - Cache de listados con Redis
   - Optimización de imágenes (thumbnails)
   - Paginación (ya implementada)

3. **SEO:**
   - Los campos `meta_title` y `meta_description` están listos
   - Implementar sitemap.xml
   - Implementar structured data (JSON-LD)

### 📋 TODO / Mejoras Futuras

- [ ] Editor WYSIWYG para contenido (CKEditor, TinyMCE)
- [ ] Sistema de comentarios
- [ ] Compartir en redes sociales
- [ ] Newsletter/Suscripción
- [ ] Artículos relacionados
- [ ] Versiones en múltiples idiomas
- [ ] Programación de publicaciones
- [ ] Analytics integrado
- [ ] Buscador con Elasticsearch

### 🐛 Troubleshooting

**Error: "django_filters not found"**
```bash
pip install django-filter
```

**Error: "Cannot write mode RGBA as JPEG"**
- Pillow intenta guardar PNG como JPG
- Convertir imagen o usar PNG

**Imágenes no se muestran:**
- Verificar `MEDIA_ROOT` y `MEDIA_URL` en settings
- En desarrollo, agregar a urls.py:
```python
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### 📞 Soporte

Para consultas sobre el sistema de blog, revisar:
1. Este archivo de documentación
2. Código en `blog/models.py` (docstrings)
3. Admin en http://localhost:8000/admin/blog/
4. API browsable en http://localhost:8000/api/v1/blog/

---

**Última actualización:** 2024-12-13
**Versión:** 1.0.0
**Autor:** StudioZens Development Team
