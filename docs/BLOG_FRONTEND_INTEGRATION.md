# Integración del Blog con Frontend

Guía para integrar el sistema de blog en el frontend de StudioZens.

## 📋 Endpoints Disponibles

### Base URL
```
http://localhost:8000/api/v1/blog
```

En producción:
```
https://tudominio.com/api/v1/blog
```

---

## 🎨 Páginas Recomendadas

### 1. Página Principal del Blog (`/blog`)

**Componentes sugeridos:**
- Header del blog
- Lista de artículos destacados (carrusel o grid)
- Lista de artículos recientes (grid con paginación)
- Sidebar con categorías y tags populares

**Endpoints a usar:**
```javascript
// Artículos destacados
GET /api/v1/blog/articles/featured/

// Artículos recientes (paginados)
GET /api/v1/blog/articles/?page=1

// Categorías
GET /api/v1/blog/categories/

// Tags
GET /api/v1/blog/tags/
```

**Ejemplo en React:**
```jsx
import { useState, useEffect } from 'react';

function BlogPage() {
  const [featured, setFeatured] = useState([]);
  const [articles, setArticles] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [featuredRes, articlesRes, categoriesRes] = await Promise.all([
          fetch('http://localhost:8000/api/v1/blog/articles/featured/'),
          fetch('http://localhost:8000/api/v1/blog/articles/'),
          fetch('http://localhost:8000/api/v1/blog/categories/')
        ]);

        setFeatured(await featuredRes.json());
        setArticles((await articlesRes.json()).results);
        setCategories((await categoriesRes.json()).results);
      } catch (error) {
        console.error('Error cargando blog:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) return <div>Cargando...</div>;

  return (
    <div className="blog-page">
      {/* Artículos destacados */}
      <section className="featured-section">
        <h2>Artículos Destacados</h2>
        <div className="featured-grid">
          {featured.map(article => (
            <FeaturedArticleCard key={article.id} article={article} />
          ))}
        </div>
      </section>

      {/* Artículos recientes */}
      <section className="articles-section">
        <h2>Últimos Artículos</h2>
        <div className="articles-grid">
          {articles.map(article => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
      </section>

      {/* Sidebar con categorías */}
      <aside className="blog-sidebar">
        <h3>Categorías</h3>
        <ul>
          {categories.map(cat => (
            <li key={cat.id}>
              <a href={`/blog/categoria/${cat.slug}`}>
                {cat.name} ({cat.articles_count})
              </a>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
```

---

### 2. Card de Artículo (Componente Reutilizable)

```jsx
function ArticleCard({ article }) {
  return (
    <article className="article-card">
      {article.cover_image_url && (
        <img
          src={article.cover_image_url}
          alt={article.cover_image_alt || article.title}
          className="article-cover"
        />
      )}

      <div className="article-content">
        <div className="article-meta">
          <span className="category">{article.category_name}</span>
          <span className="reading-time">{article.reading_time_minutes} min</span>
        </div>

        <h3 className="article-title">{article.title}</h3>
        <p className="article-subtitle">{article.subtitle}</p>
        <p className="article-excerpt">{article.excerpt}</p>

        <div className="article-tags">
          {article.tags.map(tag => (
            <span key={tag.id} className="tag">{tag.name}</span>
          ))}
        </div>

        <div className="article-footer">
          <span className="author">{article.author_display}</span>
          <span className="date">
            {new Date(article.published_at).toLocaleDateString('es-CO', {
              year: 'numeric',
              month: 'long',
              day: 'numeric'
            })}
          </span>
        </div>

        <a href={`/blog/${article.slug}`} className="read-more">
          Leer más →
        </a>
      </div>
    </article>
  );
}
```

---

### 3. Página de Detalle del Artículo (`/blog/:slug`)

**Endpoint:**
```javascript
GET /api/v1/blog/articles/{slug}/
```

**Ejemplo en React:**
```jsx
import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';

function ArticleDetailPage() {
  const { slug } = useParams();
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchArticle = async () => {
      try {
        const response = await fetch(
          `http://localhost:8000/api/v1/blog/articles/${slug}/`
        );
        const data = await response.json();
        setArticle(data);
      } catch (error) {
        console.error('Error cargando artículo:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchArticle();
  }, [slug]);

  if (loading) return <div>Cargando artículo...</div>;
  if (!article) return <div>Artículo no encontrado</div>;

  return (
    <article className="article-detail">
      {/* Header con imagen de portada */}
      {article.cover_image_url && (
        <div className="article-header">
          <img
            src={article.cover_image_url}
            alt={article.cover_image_alt || article.title}
            className="cover-image"
          />
        </div>
      )}

      {/* Metadata */}
      <div className="article-meta">
        <span className="category">{article.category.name}</span>
        <span className="reading-time">
          {article.reading_time_minutes} minutos de lectura
        </span>
        <span className="views">{article.views_count} vistas</span>
      </div>

      {/* Título y subtítulo */}
      <h1 className="article-title">{article.title}</h1>
      {article.subtitle && (
        <p className="article-subtitle">{article.subtitle}</p>
      )}

      {/* Autor y fecha */}
      <div className="article-byline">
        <span className="author">Por {article.author_display}</span>
        <span className="date">
          {new Date(article.published_at).toLocaleDateString('es-CO', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          })}
        </span>
      </div>

      {/* Contenido */}
      <div
        className="article-body"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />

      {/* Galería de imágenes (si las hay) */}
      {article.images && article.images.length > 0 && (
        <div className="article-gallery">
          <h3>Galería</h3>
          <div className="gallery-grid">
            {article.images.map(img => (
              <figure key={img.id}>
                <img src={img.image_url} alt={img.alt_text} />
                {img.caption && <figcaption>{img.caption}</figcaption>}
              </figure>
            ))}
          </div>
        </div>
      )}

      {/* Tags */}
      <div className="article-tags">
        <h4>Etiquetas:</h4>
        {article.tags.map(tag => (
          <a key={tag.id} href={`/blog/tag/${tag.slug}`} className="tag">
            {tag.name}
          </a>
        ))}
      </div>

      {/* Compartir en redes sociales (opcional) */}
      <div className="article-share">
        <h4>Compartir:</h4>
        <button onClick={() => shareOnFacebook(article)}>Facebook</button>
        <button onClick={() => shareOnTwitter(article)}>Twitter</button>
        <button onClick={() => shareOnWhatsApp(article)}>WhatsApp</button>
      </div>
    </article>
  );
}
```

---

### 4. Página de Categoría (`/blog/categoria/:slug`)

**Endpoint:**
```javascript
GET /api/v1/blog/articles/?category__slug={slug}
```

**Ejemplo:**
```jsx
function CategoryPage() {
  const { slug } = useParams();
  const [category, setCategory] = useState(null);
  const [articles, setArticles] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      const [catRes, articlesRes] = await Promise.all([
        fetch(`http://localhost:8000/api/v1/blog/categories/${slug}/`),
        fetch(`http://localhost:8000/api/v1/blog/articles/?category__slug=${slug}`)
      ]);

      setCategory(await catRes.json());
      setArticles((await articlesRes.json()).results);
    };

    fetchData();
  }, [slug]);

  return (
    <div className="category-page">
      <h1>{category?.name}</h1>
      <p>{category?.description}</p>

      <div className="articles-grid">
        {articles.map(article => (
          <ArticleCard key={article.id} article={article} />
        ))}
      </div>
    </div>
  );
}
```

---

### 5. Búsqueda de Artículos

**Endpoint:**
```javascript
GET /api/v1/blog/articles/?search={query}
```

**Ejemplo:**
```jsx
function BlogSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/blog/articles/?search=${encodeURIComponent(query)}`
      );
      const data = await response.json();
      setResults(data.results);
    } catch (error) {
      console.error('Error en búsqueda:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="blog-search">
      <form onSubmit={handleSearch}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar artículos..."
        />
        <button type="submit">Buscar</button>
      </form>

      {loading && <div>Buscando...</div>}

      <div className="search-results">
        {results.map(article => (
          <ArticleCard key={article.id} article={article} />
        ))}
        {results.length === 0 && !loading && (
          <p>No se encontraron artículos</p>
        )}
      </div>
    </div>
  );
}
```

---

## 🎯 Filtros y Ordenamiento

### Filtros Disponibles

```javascript
// Por categoría
GET /api/v1/blog/articles/?category__slug=ayurveda

// Por etiqueta
GET /api/v1/blog/articles/?tags__slug=masajes

// Solo destacados
GET /api/v1/blog/articles/?is_featured=true

// Búsqueda
GET /api/v1/blog/articles/?search=meditacion

// Combinación de filtros
GET /api/v1/blog/articles/?category__slug=spa&is_featured=true
```

### Ordenamiento

```javascript
// Más recientes primero (default)
GET /api/v1/blog/articles/?ordering=-published_at

// Más antiguos primero
GET /api/v1/blog/articles/?ordering=published_at

// Más vistos
GET /api/v1/blog/articles/?ordering=-views_count

// Por título (A-Z)
GET /api/v1/blog/articles/?ordering=title
```

### Paginación

```javascript
// Página específica
GET /api/v1/blog/articles/?page=2

// Cambiar tamaño de página (si está configurado)
GET /api/v1/blog/articles/?page=1&page_size=10
```

---

## 📱 Componente de Paginación

```jsx
function Pagination({ count, next, previous, onPageChange }) {
  const totalPages = Math.ceil(count / 20); // 20 es el page_size default
  const [currentPage, setCurrentPage] = useState(1);

  const handlePageChange = (page) => {
    setCurrentPage(page);
    onPageChange(page);
  };

  return (
    <div className="pagination">
      <button
        onClick={() => handlePageChange(currentPage - 1)}
        disabled={!previous}
      >
        Anterior
      </button>

      <span>Página {currentPage} de {totalPages}</span>

      <button
        onClick={() => handlePageChange(currentPage + 1)}
        disabled={!next}
      >
        Siguiente
      </button>
    </div>
  );
}
```

---

## 🎨 Estilos CSS Sugeridos

```css
/* Card de artículo */
.article-card {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: transform 0.2s;
}

.article-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.article-cover {
  width: 100%;
  height: 200px;
  object-fit: cover;
}

.article-title {
  font-size: 1.5rem;
  margin: 1rem 0 0.5rem;
  color: #333;
}

.article-subtitle {
  font-size: 1rem;
  color: #666;
  margin-bottom: 0.5rem;
}

.article-excerpt {
  font-size: 0.9rem;
  color: #777;
  line-height: 1.6;
}

/* Tags */
.article-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 1rem 0;
}

.tag {
  background: #f0f0f0;
  padding: 0.25rem 0.75rem;
  border-radius: 16px;
  font-size: 0.85rem;
  color: #555;
}

/* Detalle del artículo */
.article-body {
  font-size: 1.1rem;
  line-height: 1.8;
  color: #333;
  max-width: 800px;
  margin: 2rem auto;
}

.article-body img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 2rem 0;
}

.article-body h2 {
  margin-top: 2rem;
  color: #2c5f2d;
}

.article-body p {
  margin-bottom: 1.5rem;
}
```

---

## 🔍 SEO Considerations

### Meta Tags

```jsx
import { Helmet } from 'react-helmet';

function ArticleDetailPage({ article }) {
  return (
    <>
      <Helmet>
        <title>{article.meta_title || article.title} | StudioZens Blog</title>
        <meta
          name="description"
          content={article.meta_description || article.excerpt}
        />
        <meta property="og:title" content={article.title} />
        <meta property="og:description" content={article.excerpt} />
        <meta property="og:image" content={article.cover_image_url} />
        <meta property="og:type" content="article" />
        <meta property="article:published_time" content={article.published_at} />
        <meta property="article:author" content={article.author_display} />
        {article.tags.map(tag => (
          <meta key={tag.id} property="article:tag" content={tag.name} />
        ))}
      </Helmet>

      {/* Contenido del artículo */}
    </>
  );
}
```

---

## 🚀 Optimizaciones

### 1. Lazy Loading de Imágenes

```jsx
function LazyImage({ src, alt, ...props }) {
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      {...props}
    />
  );
}
```

### 2. Caché con React Query

```jsx
import { useQuery } from 'react-query';

function useBlogArticles(filters = {}) {
  return useQuery(['articles', filters], async () => {
    const params = new URLSearchParams(filters);
    const response = await fetch(
      `http://localhost:8000/api/v1/blog/articles/?${params}`
    );
    return response.json();
  }, {
    staleTime: 5 * 60 * 1000, // 5 minutos
    cacheTime: 10 * 60 * 1000, // 10 minutos
  });
}

// Uso
function BlogPage() {
  const { data, isLoading, error } = useBlogArticles();

  if (isLoading) return <div>Cargando...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      {data.results.map(article => (
        <ArticleCard key={article.id} article={article} />
      ))}
    </div>
  );
}
```

---

## 📦 Librerías Recomendadas

```bash
# React Router para navegación
npm install react-router-dom

# React Query para caché y fetching
npm install @tanstack/react-query

# React Helmet para SEO
npm install react-helmet

# Markdown renderer (si usas markdown en contenido)
npm install react-markdown

# Syntax highlighting para código
npm install react-syntax-highlighter
```

---

## ✅ Checklist de Implementación

- [ ] Crear página principal del blog (`/blog`)
- [ ] Crear componente de card de artículo
- [ ] Crear página de detalle (`/blog/:slug`)
- [ ] Crear página de categoría (`/blog/categoria/:slug`)
- [ ] Crear página de etiqueta (`/blog/tag/:slug`)
- [ ] Implementar búsqueda
- [ ] Implementar paginación
- [ ] Agregar meta tags para SEO
- [ ] Optimizar imágenes (lazy loading)
- [ ] Agregar compartir en redes sociales
- [ ] Responsive design
- [ ] Testing

---

## 🎉 Resultado Final

Con esta guía podrás integrar completamente el sistema de blog en tu frontend y tener:

- ✅ Página principal con artículos destacados y recientes
- ✅ Páginas de detalle con contador de vistas
- ✅ Filtrado por categorías y etiquetas
- ✅ Búsqueda de artículos
- ✅ SEO optimizado
- ✅ Responsive y performante

---

**Última actualización:** 13 de Diciembre, 2024
