import hashlib
import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from core.decorators import idempotent_view
from core.models import IdempotencyKey


class DummyIdempotentView(APIView):
    call_count = 0

    @idempotent_view(timeout=1)
    def post(self, request):
        DummyIdempotentView.call_count += 1
        return Response({"echo": request.data.get("value")}, status=201)


@pytest.mark.django_db
def test_idempotent_view_without_header_calls_through(admin_user):
    DummyIdempotentView.call_count = 0
    IdempotencyKey.objects.all().delete()
    factory = APIRequestFactory()
    view = DummyIdempotentView.as_view()

    request = factory.post("/endpoint/", {"value": "plain"}, format="json")
    force_authenticate(request, user=admin_user)
    response = view(request)

    assert response.status_code == 201
    assert DummyIdempotentView.call_count == 1
    assert IdempotencyKey.objects.count() == 0


@pytest.mark.django_db
def test_idempotent_view_caches_completed_response(admin_user):
    DummyIdempotentView.call_count = 0
    factory = APIRequestFactory()
    view = DummyIdempotentView.as_view()

    request1 = factory.post("/endpoint/", {"value": "one"}, format="json", HTTP_IDEMPOTENCY_KEY="key-1234567890123")
    force_authenticate(request1, user=admin_user)
    response1 = view(request1)

    assert response1.status_code == 201
    assert DummyIdempotentView.call_count == 1
    record = IdempotencyKey.objects.get(key="key-1234567890123")
    assert record.status == IdempotencyKey.Status.COMPLETED
    assert record.response_body["echo"] == "one"

    # Segunda llamada debe devolver la respuesta cacheada sin ejecutar la vista
    request2 = factory.post("/endpoint/", {"value": "one"}, format="json", HTTP_IDEMPOTENCY_KEY="key-1234567890123")
    force_authenticate(request2, user=admin_user)
    response2 = view(request2)

    assert response2.data == {"echo": "one"}
    assert DummyIdempotentView.call_count == 1


@pytest.mark.django_db
def test_idempotent_view_detects_payload_mismatch(admin_user):
    DummyIdempotentView.call_count = 0
    factory = APIRequestFactory()
    view = DummyIdempotentView.as_view()

    request1 = factory.post("/endpoint/", {"value": "one"}, format="json", HTTP_IDEMPOTENCY_KEY="key-mismatch-00123")
    force_authenticate(request1, user=admin_user)
    view(request1)

    request2 = factory.post("/endpoint/", {"value": "two"}, format="json", HTTP_IDEMPOTENCY_KEY="key-mismatch-00123")
    force_authenticate(request2, user=admin_user)
    response2 = view(request2)

    assert response2.status_code == 422
    assert response2.data["code"] == "IDEMPOTENCY_KEY_MISMATCH"
    assert DummyIdempotentView.call_count == 1


@pytest.mark.django_db
def test_idempotent_view_handles_pending_states(admin_user):
    DummyIdempotentView.call_count = 0
    factory = APIRequestFactory()
    view = DummyIdempotentView.as_view()
    data = {"value": "slow"}
    request_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    # Clave pendiente reciente => 409
    IdempotencyKey.objects.create(
        key="key-pending-123456",
        endpoint="/endpoint/",
        status=IdempotencyKey.Status.PENDING,
        locked_at=timezone.now(),
        request_hash=request_hash,
    )
    request = factory.post("/endpoint/", data, format="json", HTTP_IDEMPOTENCY_KEY="key-pending-123456")
    force_authenticate(request, user=admin_user)
    response = view(request)
    assert response.status_code == 409
    assert DummyIdempotentView.call_count == 0  # no se ejecutó la vista

    # Clave pendiente expirada => se reintenta y completa
    IdempotencyKey.objects.create(
        key="key-pending-old-123",
        endpoint="/endpoint/",
        status=IdempotencyKey.Status.PENDING,
        locked_at=timezone.now() - timedelta(seconds=120),
        request_hash=request_hash,
    )
    request_old = factory.post("/endpoint/", data, format="json", HTTP_IDEMPOTENCY_KEY="key-pending-old-123")
    force_authenticate(request_old, user=admin_user)
    response_old = view(request_old)
    assert response_old.status_code == 201
    record = IdempotencyKey.objects.get(key="key-pending-old-123")
    assert record.status == IdempotencyKey.Status.COMPLETED
    assert DummyIdempotentView.call_count == 1


class ErrorView(APIView):
    @idempotent_view()
    def post(self, request):
        raise ValueError("boom")


@pytest.mark.django_db
def test_idempotent_view_cleans_up_on_exception(admin_user):
    factory = APIRequestFactory()
    view = ErrorView.as_view()

    request = factory.post("/endpoint/", {"value": "err"}, format="json", HTTP_IDEMPOTENCY_KEY="key-error-1234567")
    force_authenticate(request, user=admin_user)

    with pytest.raises(ValueError):
        view(request)

    assert not IdempotencyKey.objects.filter(key="key-error-1234567").exists()


@pytest.mark.django_db
def test_idempotent_view_skips_non_mutating_methods(admin_user):
    class GetOnlyView(APIView):
        call_count = 0

        @idempotent_view()
        def get(self, request):
            GetOnlyView.call_count += 1
            return Response({"ok": True}, status=200)

    factory = APIRequestFactory()
    view = GetOnlyView.as_view()

    request = factory.get("/endpoint/", HTTP_IDEMPOTENCY_KEY="key-get-123456")
    force_authenticate(request, user=admin_user)
    response = view(request)

    assert response.status_code == 200
    assert GetOnlyView.call_count == 1
    assert IdempotencyKey.objects.filter(key="key-get-123456").count() == 0


@pytest.mark.django_db
def test_idempotent_view_handles_unserializable_body(admin_user):
    class UnserializableView(APIView):
        @idempotent_view()
        def post(self, request):
            return Response({"ok": True}, status=201)

    factory = APIRequestFactory()
    view = UnserializableView.as_view()

    request = factory.post("/endpoint/", {}, format="json", HTTP_IDEMPOTENCY_KEY="key-unserializable-1")
    # Inyectar datos no serializables para disparar la ruta de except en el hash
    request.data = {"value": {1, 2}}
    force_authenticate(request, user=admin_user)
    response = view(request)

    assert response.status_code == 201
    assert IdempotencyKey.objects.filter(key="key-unserializable-1").exists()


@pytest.mark.django_db
def test_idempotent_view_returns_response_if_record_missing_after_view(admin_user):
    class DeletingView(APIView):
        @idempotent_view()
        def post(self, request):
            # Simula limpieza externa del registro antes de marcar completado
            IdempotencyKey.objects.filter(key=request.headers.get("Idempotency-Key")).delete()
            return Response({"ok": True}, status=200)

    factory = APIRequestFactory()
    view = DeletingView.as_view()

    request = factory.post("/endpoint/", {"v": 1}, format="json", HTTP_IDEMPOTENCY_KEY="key-deleting-1")
    force_authenticate(request, user=admin_user)
    response = view(request)

    assert response.status_code == 200
