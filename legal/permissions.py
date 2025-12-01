from rest_framework import permissions

from .models import LegalDocument, UserConsent


def consent_required_permission(doc_type, context_type=None):
    """
    Devuelve una clase de permiso parametrizada para exigir el consentimiento
    de la versión activa de un tipo de documento legal.
    """
    class HasAcceptedLatestDocument(permissions.BasePermission):
        message = "Debes aceptar los términos y condiciones antes de continuar."
        required_doc_type = doc_type
        required_context_type = context_type

        def has_permission(self, request, view):
            required_doc = self.required_doc_type
            if not required_doc:
                return True

            latest_doc = (
                LegalDocument.objects.filter(doc_type=required_doc, is_active=True)
                .order_by("-version")
                .first()
            )
            # Si no hay documento activo, no se bloquea.
            if not latest_doc:
                return True

            user = getattr(request, "user", None)
            if not user or not user.is_authenticated:
                self.message = "Autenticación requerida para validar términos."
                return False

            qs = UserConsent.objects.filter(
                user=user,
                document=latest_doc,
                document_version=latest_doc.version,
                is_valid=True,
            )
            if self.required_context_type:
                qs = qs.filter(context_type=self.required_context_type)

            if qs.exists():
                return True

            self.message = f"Debes aceptar {latest_doc.title} v{latest_doc.version}."
            return False

    return HasAcceptedLatestDocument
