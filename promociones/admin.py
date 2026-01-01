from django.contrib import admin
from django.utils.html import format_html
from .models import Promocion


@admin.register(Promocion)
class PromocionAdmin(admin.ModelAdmin):
    list_display = [
        'estado_visual',
        'titulo',
        'tipo',
        'paginas_display',
        'prioridad',
        'fecha_inicio',
        'fecha_fin',
        'estadisticas',
    ]
    list_filter = [
        'activa',
        'tipo',
        'fecha_inicio',
        'fecha_fin',
    ]
    search_fields = ['titulo', 'descripcion']
    readonly_fields = [
        'veces_mostrada',
        'veces_clickeada',
        'creada_en',
        'actualizada_en',
        'preview_imagen',
    ]

    fieldsets = (
        ('Información Principal', {
            'fields': (
                'titulo',
                'descripcion',
                'imagen',
                'preview_imagen',
            )
        }),
        ('Configuración de Visualización', {
            'fields': (
                'tipo',
                'paginas',
                'mostrar_siempre',
                'prioridad',
            )
        }),
        ('Activación y Vigencia', {
            'fields': (
                'activa',
                'fecha_inicio',
                'fecha_fin',
            )
        }),
        ('Botón de Acción (Opcional)', {
            'fields': (
                'texto_boton',
                'link_accion',
            ),
            'classes': ('collapse',),
        }),
        ('Estadísticas', {
            'fields': (
                'veces_mostrada',
                'veces_clickeada',
                'creada_en',
                'actualizada_en',
            ),
            'classes': ('collapse',),
        }),
    )

    def estado_visual(self, obj):
        """Muestra un indicador visual del estado de la promoción."""
        if obj.esta_vigente():
            return format_html(
                '<span style="color: green; font-weight: bold;">✅ ACTIVA</span>'
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">❌ INACTIVA</span>'
        )
    estado_visual.short_description = 'Estado'

    def estadisticas(self, obj):
        """Muestra las estadísticas de forma visual."""
        return format_html(
            '👁️ {} | 🖱️ {}',
            obj.veces_mostrada,
            obj.veces_clickeada
        )
    estadisticas.short_description = 'Estadísticas (Vistas | Clics)'

    def preview_imagen(self, obj):
        """Muestra una preview de la imagen en el admin."""
        if obj.imagen:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 200px;" />',
                obj.imagen.url
            )
        return "Sin imagen"
    preview_imagen.short_description = 'Vista previa de imagen'

    class Media:
        css = {
            'all': ('admin/css/promociones_admin.css',)
        }
        js = ('admin/js/promociones_admin.js',)

    def get_form(self, request, obj=None, **kwargs):
        """Personaliza el formulario del admin."""
        form = super().get_form(request, obj, **kwargs)

        # Ayuda contextual para el campo paginas
        if 'paginas' in form.base_fields:
            form.base_fields['paginas'].help_text = (
                'Selecciona las páginas donde se mostrará esta promoción. '
                'Opciones: "dashboard", "home", "servicios". '
                'Ejemplo: ["dashboard", "home"]'
            )

        return form
