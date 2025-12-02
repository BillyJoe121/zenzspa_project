
import pytest
from django.test import RequestFactory
from django.http import HttpResponse
from rest_framework.test import APIClient
from model_bakery import baker

from legal.models import LegalDocument, UserConsent
from legal.middleware import LegalConsentRequiredMiddleware
from legal.views import LegalDocumentViewSet
from users.models import CustomUser

@pytest.mark.django_db
class TestLegalDocumentInvalidation:
    def test_save_invalidates_previous_consents(self):
        # Create v1
        doc1 = LegalDocument.objects.create(
            slug="terms-test",
            title="Terms v1",
            body="Body v1",
            version=1,
            is_active=True
        )
        user = baker.make(CustomUser)
        
        # Create consent for v1
        consent = UserConsent.objects.create(
            document=doc1,
            document_version=1,
            user=user,
            context_type=UserConsent.ContextType.GLOBAL
        )
        
        assert consent.is_valid is True
        
        # Create v2
        doc2 = LegalDocument.objects.create(
            slug="terms-test",
            title="Terms v2",
            body="Body v2",
            version=2,
            is_active=True
        )
        
        # Check invalidation
        consent.refresh_from_db()
        assert consent.is_valid is False

@pytest.mark.django_db
class TestLegalViewsExtended:
    def test_legal_document_viewset_queryset_admin(self):
        admin = baker.make(CustomUser, role=CustomUser.Role.ADMIN)
        doc_active = baker.make(LegalDocument, is_active=True)
        doc_inactive = baker.make(LegalDocument, is_active=False)
        
        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get("/api/v1/legal/documents/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 2

    def test_legal_document_viewset_queryset_user(self):
        user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)
        doc_active = baker.make(LegalDocument, is_active=True)
        doc_inactive = baker.make(LegalDocument, is_active=False)
        
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/v1/legal/documents/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == str(doc_active.id)

    def test_legal_document_viewset_filtering(self):
        user = baker.make(CustomUser)
        doc1 = baker.make(LegalDocument, slug="slug1", doc_type="GLOBAL_POPUP", is_active=True)
        doc2 = baker.make(LegalDocument, slug="slug2", doc_type="PURCHASE", is_active=True)
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Filter by slug
        resp = client.get("/api/v1/legal/documents/?slug=slug1")
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["id"] == str(doc1.id)
        
        # Filter by doc_type
        resp = client.get("/api/v1/legal/documents/?doc_type=PURCHASE")
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["id"] == str(doc2.id)

@pytest.mark.django_db
class TestLegalMiddlewareExtended:
    def test_middleware_skips_prefixes(self):
        middleware = LegalConsentRequiredMiddleware(lambda r: HttpResponse("OK"))
        factory = RequestFactory()
        request = factory.get("/admin/login/")
        request.user = baker.make(CustomUser)
        
        response = middleware.process_request(request)
        assert response is None

    def test_middleware_skips_unauthenticated(self):
        middleware = LegalConsentRequiredMiddleware(lambda r: HttpResponse("OK"))
        factory = RequestFactory()
        request = factory.get("/api/v1/secure")
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        
        response = middleware.process_request(request)
        assert response is None

    def test_middleware_no_active_doc(self):
        middleware = LegalConsentRequiredMiddleware(lambda r: HttpResponse("OK"))
        factory = RequestFactory()
        request = factory.get("/api/v1/secure")
        request.user = baker.make(CustomUser)
        
        # No documents exist
        response = middleware.process_request(request)
        assert response is None
