from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin
from .models import Article, Category, Tag, ArticleImage


class ArticleImageInline(admin.TabularInline):
    """Inline para agregar imágenes al artículo"""
    model = ArticleImage
    extra = 1
    fields = ['image', 'alt_text', 'caption', 'order']
    ordering = ['order']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin para categorías"""
    list_display = ['name', 'slug', 'articles_count', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']

    def articles_count(self, obj):
        return obj.articles.count()
    articles_count.short_description = 'Artículos'


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Admin para etiquetas"""
    list_display = ['name', 'slug', 'articles_count', 'created_at']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at']

    def articles_count(self, obj):
        return obj.articles.count()
    articles_count.short_description = 'Artículos'


@admin.register(Article)
class ArticleAdmin(SimpleHistoryAdmin):
    """Admin para artículos con todas las funcionalidades"""
    list_display = [
        'title',
        'status_badge',
        'category',
        'author_display',
        'published_at',
        'views_count',
        'is_featured',
        'created_at'
    ]
    list_filter = [
        'status',
        'is_featured',
        'category',
        'tags',
        'created_at',
        'published_at'
    ]
    search_fields = ['title', 'subtitle', 'content', 'excerpt']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = [
        'slug',
        'views_count',
        'reading_time_minutes',
        'created_at',
        'updated_at',
        'cover_preview'
    ]
    filter_horizontal = ['tags']
    date_hierarchy = 'published_at'
    inlines = [ArticleImageInline]

    fieldsets = (
        ('Información Básica', {
            'fields': (
                'title',
                'slug',
                'subtitle',
                'excerpt',
                'content',
            )
        }),
        ('Portada', {
            'fields': (
                'cover_image',
                'cover_preview',
                'cover_image_alt',
            )
        }),
        ('Clasificación', {
            'fields': (
                'category',
                'tags',
            )
        }),
        ('Autor', {
            'fields': (
                'author',
                'author_name',
            )
        }),
        ('Publicación', {
            'fields': (
                'status',
                'published_at',
            )
        }),
        ('SEO', {
            'fields': (
                'meta_title',
                'meta_description',
            ),
            'classes': ('collapse',)
        }),
        ('Destacado', {
            'fields': (
                'is_featured',
                'featured_order',
            )
        }),
        ('Métricas', {
            'fields': (
                'views_count',
                'reading_time_minutes',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    actions = ['publish_articles', 'unpublish_articles', 'feature_articles', 'unfeature_articles']

    def status_badge(self, obj):
        """Muestra un badge visual del estado"""
        colors = {
            'published': '#28a745',
            'draft': '#6c757d',
            'archived': '#ffc107'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Estado'

    def author_display(self, obj):
        """Muestra el nombre del autor"""
        return obj.get_author_display()
    author_display.short_description = 'Autor'

    def cover_preview(self, obj):
        """Preview de la imagen de portada"""
        if obj.cover_image:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 200px; border-radius: 5px;" />',
                obj.cover_image.url
            )
        return "Sin imagen"
    cover_preview.short_description = 'Preview de portada'

    def save_model(self, request, obj, form, change):
        """Auto-asignar autor si no existe"""
        if not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    # Actions personalizadas
    def publish_articles(self, request, queryset):
        """Publicar artículos seleccionados"""
        updated = 0
        for article in queryset:
            if article.status != 'published':
                article.status = 'published'
                if not article.published_at:
                    article.published_at = timezone.now()
                article.save()
                updated += 1

        self.message_user(request, f'{updated} artículo(s) publicado(s) exitosamente.')
    publish_articles.short_description = 'Publicar artículos seleccionados'

    def unpublish_articles(self, request, queryset):
        """Despublicar artículos seleccionados (cambiar a borrador)"""
        updated = queryset.filter(status='published').update(status='draft')
        self.message_user(request, f'{updated} artículo(s) cambiado(s) a borrador.')
    unpublish_articles.short_description = 'Cambiar a borrador'

    def feature_articles(self, request, queryset):
        """Marcar como destacados"""
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'{updated} artículo(s) marcado(s) como destacado(s).')
    feature_articles.short_description = 'Marcar como destacados'

    def unfeature_articles(self, request, queryset):
        """Quitar de destacados"""
        updated = queryset.update(is_featured=False)
        self.message_user(request, f'{updated} artículo(s) removido(s) de destacados.')
    unfeature_articles.short_description = 'Quitar de destacados'


@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    """Admin para imágenes de artículos"""
    list_display = ['id', 'article', 'image_preview', 'alt_text', 'order', 'created_at']
    list_filter = ['article', 'created_at']
    search_fields = ['article__title', 'alt_text', 'caption']
    readonly_fields = ['created_at', 'image_preview']
    ordering = ['article', 'order']

    def image_preview(self, obj):
        """Preview de la imagen"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 150px; max-height: 100px; border-radius: 3px;" />',
                obj.image.url
            )
        return "Sin imagen"
    image_preview.short_description = 'Preview'
