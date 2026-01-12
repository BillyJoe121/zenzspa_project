from rest_framework import serializers


def _show_sensitive_data(context):
    """Determina si el usuario autenticado puede ver campos sensibles."""
    request = context.get("request") if context else None
    user = getattr(request, "user", None)
    return bool(user and getattr(user, "is_authenticated", False))


class ImageUrlMixin(serializers.ModelSerializer):
    """Mixin para exponer url efectiva de imágenes."""

    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        return obj.get_image_url()
