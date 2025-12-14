# Blog App - StudioZens

Sistema completo de blog con API REST y panel de administración.

## Inicio Rápido

### 1. Poblar con datos de prueba
```bash
python manage.py seed_blog
```

### 2. Acceder al admin
http://localhost:8000/admin/blog/

### 3. Ver API
- Lista de artículos: http://localhost:8000/api/v1/blog/articles/
- Categorías: http://localhost:8000/api/v1/blog/categories/
- Etiquetas: http://localhost:8000/api/v1/blog/tags/

## Endpoints Principales

### Públicos
- `GET /api/v1/blog/articles/` - Artículos publicados
- `GET /api/v1/blog/articles/{slug}/` - Detalle (incrementa vistas)
- `GET /api/v1/blog/articles/featured/` - Destacados
- `GET /api/v1/blog/articles/recent/` - Recientes
- `GET /api/v1/blog/articles/popular/` - Más vistos

### Admin (requiere autenticación + staff)
- `POST /api/v1/blog/articles/` - Crear
- `PUT/PATCH /api/v1/blog/articles/{slug}/` - Editar
- `DELETE /api/v1/blog/articles/{slug}/` - Eliminar
- `POST /api/v1/blog/articles/{slug}/publish/` - Publicar
- `POST /api/v1/blog/articles/{slug}/unpublish/` - Despublicar

## Filtros

```
?category__slug=ayurveda
?tags__slug=doshas
?search=meditacion
?ordering=-published_at
?is_featured=true
```

## Modelos

- **Article** - Artículos con título, contenido, portada, SEO, métricas
- **Category** - Categorías para organización
- **Tag** - Etiquetas para clasificación
- **ArticleImage** - Galería de imágenes por artículo

## Documentación Completa

Ver: [docs/BLOG_SYSTEM.md](../docs/BLOG_SYSTEM.md)
