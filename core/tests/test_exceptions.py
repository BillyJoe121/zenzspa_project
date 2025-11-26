import pytest
from rest_framework import exceptions, status
from rest_framework.response import Response

from core import exceptions as core_exc


def test_business_logic_error_payload_and_status():
    err = core_exc.BusinessLogicError(detail="msg", internal_code="X1", extra={"a": 1}, status_code=status.HTTP_400_BAD_REQUEST)
    assert str(err.detail["detail"]) == "msg"
    assert err.detail["code"] == "X1"
    assert str(err.detail["meta"]["a"]) == "1"
    assert err.status_code == status.HTTP_400_BAD_REQUEST


def test_invalid_state_transition_error_includes_states():
    err = core_exc.InvalidStateTransitionError(current_state="pending", target_state="completed")
    assert "pending" in str(err.detail["detail"])
    assert err.detail["meta"]["current_state"] == "pending"
    assert err.detail["meta"]["target_state"] == "completed"


def test_rate_limit_exceeded_custom_message():
    err = core_exc.RateLimitExceededError(retry_after=5)
    assert "5" in err.detail
    assert err.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_drf_exception_handler_normalizes_response():
    exc = exceptions.ValidationError({"field": ["required"]})
    response = core_exc.drf_exception_handler(exc, context={})
    assert isinstance(response, Response)
    assert response.data["error"] == "VALIDATION_ERROR"
    assert response.data["status_code"] == status.HTTP_400_BAD_REQUEST
    assert "errors" in response.data

    not_found = exceptions.NotFound("missing")
    response = core_exc.drf_exception_handler(not_found, context={})
    assert response.data["error"] == "NOT_FOUND"


def test_drf_exception_handler_returns_none_for_unhandled():
    response = core_exc.drf_exception_handler(Exception("boom"), context={})
    assert response is None
