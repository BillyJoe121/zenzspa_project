from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminLegalDocumentViewSet, LegalDocumentViewSet, UserConsentViewSet

router = DefaultRouter()
router.register(r'documents', LegalDocumentViewSet, basename='legal-document')
router.register(r'consents', UserConsentViewSet, basename='user-consent')
router.register(r'admin/documents', AdminLegalDocumentViewSet, basename='admin-legal-document')

urlpatterns = [
    path('', include(router.urls)),
]
