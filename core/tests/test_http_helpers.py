import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core import pagination, routers, schema
from core.api.throttling import AdminThrottle


def test_default_pagination_response():
    factory = APIRequestFactory()
    paginator = pagination.DefaultPageNumberPagination()
    drf_request = Request(factory.get("/items/?page=2"))
    queryset = list(range(30))

    page = paginator.paginate_queryset(queryset, drf_request)
    response = paginator.get_paginated_response(page)

    assert response.data["count"] == 30
    assert response.data["page"] == 2
    assert response.data["pages"] == 2
    assert len(response.data["results"]) == 10


def test_admin_throttle_allows_non_admin_without_rate_check():
    throttle = AdminThrottle()
    request = type("Req", (), {"user": type("User", (), {"is_authenticated": False})()})()
    assert throttle.allow_request(request, view=None) is True

    request.user.is_authenticated = True
    request.user.role = "CLIENT"
    assert throttle.allow_request(request, view=None) is True


def test_admin_throttle_calls_super_for_admin(monkeypatch):
    throttle = AdminThrottle()
    request = type("Req", (), {"user": type("User", (), {"is_authenticated": True, "role": "ADMIN"})()})()

    called = {}

    def fake_allow(self, req, view):
        called["called"] = True
        return False

    monkeypatch.setattr("core.throttling.UserRateThrottle.allow_request", fake_allow)
    assert throttle.allow_request(request, view=None) is False
    assert called["called"] is True


def test_router_and_schema_helpers():
    router = routers.get_default_router()
    assert router.trailing_slash == "/"

    # Instanciar sin __init__ para llamar directamente al método
    auth_scheme = schema.SimpleJWTAuthenticationScheme.__new__(schema.SimpleJWTAuthenticationScheme)
    definition = schema.SimpleJWTAuthenticationScheme.get_security_definition(auth_scheme, auto_schema=None)
    assert definition["scheme"] == "bearer"
    assert definition["type"] == "http"
