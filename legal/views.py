from rest_framework import mixins, permissions, viewsets

from .models import LegalDocument, UserConsent
from .serializers import (
    AdminLegalDocumentSerializer,
    LegalDocumentSerializer,
    UserConsentCreateSerializer,
    UserConsentSerializer,
)


from rest_framework import mixins, permissions, viewsets
from core.permissions import IsAdmin

class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return IsAdmin().has_permission(request, view)


class LegalDocumentViewSet(viewsets.ModelViewSet):
    """
    CRUD de documentos legales.
    - Público: Solo lectura (GET).
    - Admin: CRUD completo (POST, PUT, PATCH, DELETE).
    """
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = LegalDocumentSerializer
    queryset = LegalDocument.objects.all() # Admin puede ver inactivos también

    def get_queryset(self):
        # Admin ve todo, usuarios solo activos
        user = getattr(self.request, "user", None)
        is_admin = user and user.is_authenticated and getattr(user, "role", "") == "ADMIN"
        
        if is_admin:
            qs = super().get_queryset()
        else:
            qs = LegalDocument.objects.filter(is_active=True)

        doc_type = self.request.query_params.get("doc_type")
        slug = self.request.query_params.get("slug")
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        if slug:
            qs = qs.filter(slug=slug)
        return qs.order_by("-version")


class UserConsentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Permite registrar la aceptación de términos (anon o autenticados) y consultarlos para el usuario autenticado.
    """
    queryset = UserConsent.objects.select_related("document", "user").filter(is_valid=True)
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return UserConsentCreateSerializer
        return UserConsentSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if user and user.is_authenticated:
            return self.queryset.filter(user=user)
        return self.queryset.none()

    def perform_create(self, serializer):
        serializer.save()


class AdminLegalDocumentViewSet(viewsets.ModelViewSet):
    """
    CRUD protegido para gestionar versiones de documentos legales.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminLegalDocumentSerializer
    queryset = LegalDocument.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        doc_type = self.request.query_params.get("doc_type")
        slug = self.request.query_params.get("slug")
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        if slug:
            qs = qs.filter(slug=slug)
        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.is_active:
            LegalDocument.objects.filter(slug=instance.slug).exclude(pk=instance.pk).update(is_active=False)
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.is_active:
            LegalDocument.objects.filter(slug=instance.slug).exclude(pk=instance.pk).update(is_active=False)
        return instance
