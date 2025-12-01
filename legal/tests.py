import pytest
from rest_framework.test import APIClient, APIRequestFactory

from legal.models import LegalDocument, UserConsent
from legal.middleware import LegalConsentRequiredMiddleware
from legal.permissions import consent_required_permission
from users.models import CustomUser


@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def api_rf():
    return APIRequestFactory()


@pytest.fixture
def legal_doc():
    return LegalDocument.objects.create(
        slug="terms-and-conditions",
        title="Términos Generales",
        body="Contenido",
        doc_type=LegalDocument.DocumentType.GLOBAL_POPUP,
        version=1,
    )


@pytest.mark.django_db
class TestLegalConsentsAPI:
    def test_anonymous_can_register_global_consent(self, api_client, legal_doc):
        payload = {
            "document": str(legal_doc.id),
            "context_type": UserConsent.ContextType.GLOBAL,
            "anonymous_id": "anon-123",
        }
        response = api_client.post("/api/v1/legal/consents/", payload, format="json")
        assert response.status_code == 201
        consent = UserConsent.objects.get()
        assert consent.anonymous_id == "anon-123"
        assert consent.document_version == legal_doc.version

    def test_authenticated_user_consent_is_linked_to_user(self, api_client, legal_doc):
        user = CustomUser.objects.create_user(
            phone_number="+573001112233",
            password="pass",
            role=CustomUser.Role.CLIENT,
            is_verified=True,
        )
        api_client.force_authenticate(user=user)
        payload = {
            "document": str(legal_doc.id),
            "context_type": UserConsent.ContextType.PROFILE,
            "context_id": str(user.id),
            "context_label": f"PROFILE-{user.id}",
        }
        response = api_client.post("/api/v1/legal/consents/", payload, format="json")
        assert response.status_code == 201
        consent = UserConsent.objects.get()
        assert consent.user == user
        assert consent.document_version == legal_doc.version
        assert consent.context_type == UserConsent.ContextType.PROFILE

    def test_missing_anonymous_id_is_rejected_for_anon(self, api_client, legal_doc):
        payload = {
            "document": str(legal_doc.id),
            "context_type": UserConsent.ContextType.GLOBAL,
        }
        response = api_client.post("/api/v1/legal/consents/", payload, format="json")
        assert response.status_code == 400
        assert UserConsent.objects.count() == 0

    def test_list_returns_only_authenticated_user_consents(self, api_client, legal_doc):
        user = CustomUser.objects.create_user(
            phone_number="+573004445556",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        other = CustomUser.objects.create_user(
            phone_number="+573007778889",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        UserConsent.objects.create(
            document=legal_doc,
            document_version=legal_doc.version,
            user=user,
            context_type=UserConsent.ContextType.GLOBAL,
        )
        UserConsent.objects.create(
            document=legal_doc,
            document_version=legal_doc.version,
            user=other,
            context_type=UserConsent.ContextType.GLOBAL,
        )
        api_client.force_authenticate(user=user)
        response = api_client.get("/api/v1/legal/consents/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["user"] == str(user.id)

    def test_prevents_duplicate_consent_same_context(self, api_client, legal_doc):
        user = CustomUser.objects.create_user(
            phone_number="+573000000001",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        api_client.force_authenticate(user=user)
        payload = {
            "document": str(legal_doc.id),
            "context_type": UserConsent.ContextType.ORDER,
            "context_id": "ORDER-1",
        }
        first = api_client.post("/api/v1/legal/consents/", payload, format="json")
        assert first.status_code == 201
        second = api_client.post("/api/v1/legal/consents/", payload, format="json")
        assert second.status_code == 400
        assert UserConsent.objects.count() == 1

    def test_requires_context_id_for_order_or_appointment(self, api_client, legal_doc):
        user = CustomUser.objects.create_user(
            phone_number="+573000000002",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        api_client.force_authenticate(user=user)
        payload = {
            "document": str(legal_doc.id),
            "context_type": UserConsent.ContextType.ORDER,
        }
        response = api_client.post("/api/v1/legal/consents/", payload, format="json")
        assert response.status_code == 400

    def test_permission_denies_without_consent_and_allows_with_consent(self, api_rf):
        doc = LegalDocument.objects.create(
            slug="terms-purchase",
            title="Términos de compra",
            body="contenido",
            doc_type=LegalDocument.DocumentType.PURCHASE,
            version=1,
        )
        user = CustomUser.objects.create_user(
            phone_number="+573000000003",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        perm_cls = consent_required_permission(LegalDocument.DocumentType.PURCHASE, UserConsent.ContextType.ORDER)
        request = api_rf.get("/")
        request.user = user

        dummy_view = object()
        assert perm_cls().has_permission(request, dummy_view) is False

        UserConsent.objects.create(
            document=doc,
            document_version=doc.version,
            user=user,
            context_type=UserConsent.ContextType.ORDER,
        )
        assert perm_cls().has_permission(request, dummy_view) is True

    def test_middleware_blocks_when_missing_latest_consent(self, api_rf):
        latest = LegalDocument.objects.create(
            slug="terms-global",
            title="Términos",
            body="contenido",
            doc_type=LegalDocument.DocumentType.GLOBAL_POPUP,
            version=2,
            is_active=True,
        )
        user = CustomUser.objects.create_user(
            phone_number="+573000000099",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        request = api_rf.get("/api/v1/secure-endpoint")
        request.user = user
        middleware = LegalConsentRequiredMiddleware()
        response = middleware.process_request(request)
        assert response.status_code == 428


@pytest.mark.django_db
class TestAdminLegalDocuments:
    def test_admin_can_create_new_version_and_deactivate_previous(self, api_client):
        admin = CustomUser.objects.create_user(
            phone_number="+573000000010",
            password="pass",
            role=CustomUser.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        api_client.force_authenticate(user=admin)
        v1 = {
            "slug": "terms-global",
            "title": "Términos v1",
            "body": "contenido v1",
            "doc_type": LegalDocument.DocumentType.GLOBAL_POPUP,
            "version": 1,
            "is_active": True,
        }
        resp1 = api_client.post("/api/v1/legal/admin/documents/", v1, format="json")
        assert resp1.status_code == 201

        v2 = v1 | {"version": 2, "title": "Términos v2", "body": "contenido v2", "is_active": True}
        resp2 = api_client.post("/api/v1/legal/admin/documents/", v2, format="json")
        assert resp2.status_code == 201

        doc1 = LegalDocument.objects.get(version=1, slug="terms-global")
        doc2 = LegalDocument.objects.get(version=2, slug="terms-global")
        assert doc2.is_active is True
        doc1.refresh_from_db()
        assert doc1.is_active is False

        # Consentimientos previos deben invalidarse
        user = CustomUser.objects.create_user(
            phone_number="+573000000012",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        UserConsent.objects.create(
            document=doc1,
            document_version=doc1.version,
            user=user,
            context_type=UserConsent.ContextType.GLOBAL,
        )
        # Guardar doc2 debe invalidar consents de versiones anteriores con mismo slug
        doc2.save()
        assert UserConsent.objects.filter(document=doc1, is_valid=False).exists()

    def test_non_admin_cannot_manage_documents(self, api_client):
        user = CustomUser.objects.create_user(
            phone_number="+573000000011",
            password="pass",
            role=CustomUser.Role.CLIENT,
        )
        api_client.force_authenticate(user=user)
        payload = {
            "slug": "blocked",
            "title": "No permitido",
            "body": "contenido",
            "doc_type": LegalDocument.DocumentType.GLOBAL_POPUP,
            "version": 1,
            "is_active": True,
        }
        resp = api_client.post("/api/v1/legal/admin/documents/", payload, format="json")
        assert resp.status_code == 403
