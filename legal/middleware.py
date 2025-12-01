import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .models import LegalDocument, UserConsent

logger = logging.getLogger(__name__)


class LegalConsentRequiredMiddleware(MiddlewareMixin):
    """
    Exige que usuarios autenticados hayan aceptado la última versión del documento legal global.
    Devuelve 428 Precondition Required si falta el consentimiento.
    """

    SKIP_PREFIXES = (
        "/admin",  # Admin Django
        "/api/v1/legal/consents",
        "/api/v1/legal/documents",
        "/static/",
        "/media/",
    )

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None

        path = request.path or ""
        if any(path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return None

        # Buscar último documento global activo
        latest_doc = (
            LegalDocument.objects.filter(
                doc_type=LegalDocument.DocumentType.GLOBAL_POPUP,
                is_active=True,
            )
            .order_by("-version")
            .first()
        )
        if not latest_doc:
            return None

        has_consent = UserConsent.objects.filter(
            user=user,
            document=latest_doc,
            document_version=latest_doc.version,
            is_valid=True,
        ).exists()

        if has_consent:
            return None

        logger.warning(
            "Usuario %s requiere aceptar %s v%s",
            user.id,
            latest_doc.slug,
            latest_doc.version,
        )
        return JsonResponse(
            {
                "detail": "Debes aceptar los términos actualizados.",
                "document": {
                    "slug": latest_doc.slug,
                    "version": latest_doc.version,
                    "title": latest_doc.title,
                    "id": str(latest_doc.id),
                },
            },
            status=428,
        )
