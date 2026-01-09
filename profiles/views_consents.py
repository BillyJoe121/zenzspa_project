from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import CustomUser
from users.permissions import IsAdminUser
from core.models import AuditLog
from core.utils import get_client_ip, safe_audit_log

from .models import ClinicalProfile, ConsentDocument, ConsentTemplate
from .serializers import ConsentTemplateSerializer

class ConsentTemplateViewSet(viewsets.ModelViewSet):
    queryset = ConsentTemplate.objects.all()
    serializer_class = ConsentTemplateSerializer
    
    def get_permissions(self):
        """
        Permitir lectura a usuarios autenticados,
        escritura solo a admins.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
    def get_queryset(self):
        """
        Usuarios regulares solo ven templates activos.
        Admins/Staff ven todos.
        """
        if self.request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return ConsentTemplate.objects.all()
        return ConsentTemplate.objects.filter(is_active=True)




class SignConsentView(generics.GenericAPIView):
    """
    Endpoint para que un usuario firme un consentimiento.
    CRÍTICO: Captura IP real del cliente para cumplimiento legal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        template_id = request.data.get('template_id')

        if not template_id:
            return Response(
                {"detail": "El campo 'template_id' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            template = ConsentTemplate.objects.get(id=template_id, is_active=True)
        except ConsentTemplate.DoesNotExist:
            return Response(
                {"detail": "Template de consentimiento no encontrado o inactivo."},
                status=status.HTTP_404_NOT_FOUND
            )

        profile, _ = ClinicalProfile.objects.get_or_create(user=request.user)

        # CRÍTICO - Capturar IP real del cliente
        client_ip = get_client_ip(request)

        # Verificar si ya existe un consentimiento firmado
        existing_consent = ConsentDocument.objects.filter(
            profile=profile,
            template_version=template.version,
            is_signed=True
        ).first()

        if existing_consent:
            return Response(
                {
                    "detail": "Ya existe un consentimiento firmado para esta versión.",
                    "consent_id": str(existing_consent.id),
                    "signed_at": existing_consent.signed_at.isoformat()
                },
                status=status.HTTP_409_CONFLICT
            )

        # Crear consentimiento firmado
        consent = ConsentDocument.objects.create(
            profile=profile,
            template=template,
            is_signed=True,
            signed_at=timezone.now(),
            ip_address=client_ip,
            revoked_at=None,
            revoked_reason="",
            revoked_by=None,
        )

        # Auditar firma
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=None,
            target_user=request.user,
            details={
                "action": "sign_consent",
                "consent_id": str(consent.id),
                "template_version": template.version,
                "ip_address": client_ip,
            }
        )

        return Response(
            {
                "detail": "Consentimiento firmado exitosamente.",
                "consent_id": str(consent.id),
                "template_version": template.version,
                "signed_at": consent.signed_at.isoformat(),
                "signature_hash": consent.signature_hash
            },
            status=status.HTTP_201_CREATED
        )


class RevokeConsentView(generics.GenericAPIView):
    """
    Permite revocar un consentimiento firmado.
    Usuarios pueden revocar los suyos y el staff/admin puede revocar cualquiera.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, consent_id, *args, **kwargs):
        consent = get_object_or_404(
            ConsentDocument.objects.select_related("profile__user"),
            id=consent_id,
        )
        consent_owner = consent.profile.user
        user = request.user
        is_staff = user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        if consent_owner != user and not is_staff:
            raise PermissionDenied("No tienes permiso para revocar este consentimiento.")
        if not consent.is_signed:
            return Response(
                {"detail": "El consentimiento ya está revocado o pendiente."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get("reason", "")
        consent.is_signed = False
        consent.revoked_at = timezone.now()
        consent.revoked_reason = reason[:255] if reason else ""
        consent.revoked_by = user
        consent.save(update_fields=["is_signed", "revoked_at", "revoked_reason", "revoked_by", "updated_at"])
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=user if is_staff else None,
            target_user=consent_owner,
            details={
                "action": "revoke_consent",
                "consent_id": str(consent.id),
                "reason": consent.revoked_reason,
                "performed_by": str(user.id),
            },
        )
        return Response(
            {
                "detail": "Consentimiento revocado correctamente.",
                "consent_id": str(consent.id),
                "revoked_at": consent.revoked_at.isoformat(),
                "reason": consent.revoked_reason,
            },
            status=status.HTTP_200_OK,
        )




class ExportClinicalDataView(generics.GenericAPIView):
    """
    Exporta todos los datos clínicos del usuario en formato JSON.
    COMPLIANCE: GDPR Art. 20 (Right to Data Portability)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            profile = ClinicalProfile.objects.get(user=request.user)
        except ClinicalProfile.DoesNotExist:
            return Response(
                {"detail": "No se encontró un perfil clínico para este usuario."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Construir datos de exportación
        data = {
            "user": {
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "email": request.user.email,
                "phone_number": request.user.phone_number,
            },
            "profile": {
                "dosha": profile.dosha,
                "element": profile.element,
                "diet_type": profile.diet_type,
                "sleep_quality": profile.sleep_quality,
                "activity_level": profile.activity_level,
                "medical_conditions": profile.medical_conditions,
                "allergies": profile.allergies,
                "contraindications": profile.contraindications,
                "accidents_notes": profile.accidents_notes,
                "general_notes": profile.general_notes,
            },
            "pains": [
                {
                    "body_part": pain.body_part,
                    "pain_level": pain.pain_level,
                    "periodicity": pain.periodicity,
                    "notes": pain.notes,
                    "created_at": pain.created_at.isoformat(),
                }
                for pain in profile.pains.all()
            ],
            "consents": [
                {
                    "template_version": consent.template_version,
                    "document_text": consent.document_text,
                    "is_signed": consent.is_signed,
                    "signed_at": consent.signed_at.isoformat() if consent.signed_at else None,
                    "ip_address": consent.ip_address,
                    "signature_hash": consent.signature_hash,
                    "created_at": consent.created_at.isoformat(),
                }
                for consent in profile.consents.filter(is_signed=True)
            ],
            "dosha_answers": [
                {
                    "question": answer.question.text,
                    "selected_option": answer.selected_option.text,
                    "associated_dosha": answer.selected_option.associated_dosha,
                }
                for answer in profile.dosha_answers.select_related('question', 'selected_option').all()
            ],
            "exported_at": timezone.now().isoformat(),
            "export_format_version": "1.0",
        }

        # Auditar exportación
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=None,
            target_user=request.user,
            details={
                "action": "export_clinical_data",
                "exported_at": data["exported_at"],
                "data_categories": list(data.keys())
            }
        )

        return Response(data, status=status.HTTP_200_OK)
