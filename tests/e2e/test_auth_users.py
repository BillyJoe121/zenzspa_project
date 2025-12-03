import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from profiles.models import ClinicalProfile
from users.models import BlockedPhoneNumber, CustomUser, UserSession


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def mock_recaptcha(monkeypatch):
    """
    Evita llamadas externas a Google reCAPTCHA.
    """
    monkeypatch.setattr("users.views.auth.verify_recaptcha", lambda *args, **kwargs: True)
    monkeypatch.setattr("users.views.password.verify_recaptcha", lambda *args, **kwargs: True)
    monkeypatch.setattr("users.serializers.verify_recaptcha", lambda *args, **kwargs: True)


@pytest.fixture
def twilio_stub(monkeypatch):
    """
    Reemplaza TwilioService por un stub controlable en los tests E2E.
    """

    class Stub:
        def __init__(self):
            self.sent_to = []
            self.valid_codes = set()
            self.checked = []

        def send_verification_code(self, phone_number):
            self.sent_to.append(phone_number)
            return "sent"

        def check_verification_code(self, phone_number, code):
            self.checked.append((phone_number, code))
            return code in self.valid_codes

    stub = Stub()

    def factory(*args, **kwargs):
        return stub

    monkeypatch.setattr("users.views.auth.TwilioService", factory)
    monkeypatch.setattr("users.views.password.TwilioService", factory)
    return stub


def _register_user(client, phone="+573000001001", password="Test123!@#"):
    payload = {
        "phone_number": phone,
        "email": "juan@test.com",
        "first_name": "Juan",
        "last_name": "Perez",
        "password": password,
    }
    response = client.post(reverse("otp-request"), payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    return CustomUser.objects.get(phone_number=phone)


def test_register_and_verify_creates_profile_and_session(api_client, twilio_stub):
    twilio_stub.valid_codes = {"123456"}

    user = _register_user(api_client)
    assert ClinicalProfile.objects.filter(user=user).exists()
    assert user.is_verified is False

    verify_resp = api_client.post(
        reverse("otp-confirm"),
        {"phone_number": user.phone_number, "code": "123456"},
        format="json",
    )

    assert verify_resp.status_code == status.HTTP_200_OK
    assert {"access", "refresh"} <= set(verify_resp.data.keys())

    user.refresh_from_db()
    assert user.is_verified is True
    assert UserSession.objects.filter(user=user, is_active=True).exists()


def test_register_existing_phone_is_rejected(api_client, twilio_stub):
    phone = "+573000001002"
    CustomUser.objects.create_user(phone_number=phone, password="Secret123!", first_name="Dup")

    response = api_client.post(
        reverse("otp-request"),
        {
            "phone_number": phone,
            "email": "dup@test.com",
            "first_name": "Juan",
            "last_name": "Perez",
            "password": "Secret123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "ya existe" in str(response.data["phone_number"][0]).lower()
    assert CustomUser.objects.filter(phone_number=phone).count() == 1


def test_register_blocked_phone_is_rejected(api_client, twilio_stub, monkeypatch):
    phone = "+573000001003"
    BlockedPhoneNumber.objects.create(phone_number=phone, notes="CNG")
    monkeypatch.setattr("users.serializers.send_non_grata_alert_to_admins.delay", lambda *args, **kwargs: None)

    response = api_client.post(
        reverse("otp-request"),
        {
            "phone_number": phone,
            "email": "blocked@test.com",
            "first_name": "Juan",
            "last_name": "Perez",
            "password": "Secret123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "bloqueado" in str(response.data["phone_number"][0]).lower()
    assert CustomUser.objects.filter(phone_number=phone).count() == 0


def test_login_requires_verified_user(api_client):
    phone = "+573000001004"
    CustomUser.objects.create_user(phone_number=phone, password="Secret123!", first_name="NoVerificado")

    response = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "Secret123!"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "no ha sido verificado" in str(response.data["detail"]).lower()
    assert not UserSession.objects.filter(user__phone_number=phone).exists()


def test_login_success_and_session_recorded(api_client):
    phone = "+573000001005"
    user = CustomUser.objects.create_user(
        phone_number=phone,
        password="Secret123!",
        first_name="Verificado",
        is_verified=True,
    )

    response = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "Secret123!"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert {"access", "refresh"} <= set(response.data.keys())
    assert UserSession.objects.filter(user=user, is_active=True).count() == 1


def test_refresh_requires_active_session(api_client):
    phone = "+573000001006"
    user = CustomUser.objects.create_user(
        phone_number=phone,
        password="Secret123!",
        first_name="Refresho",
        is_verified=True,
    )
    login_resp = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "Secret123!"},
        format="json",
    )
    refresh_token = login_resp.data["refresh"]
    session = UserSession.objects.get(user=user)
    session.is_active = False
    session.save(update_fields=["is_active"])

    refresh_resp = api_client.post(
        reverse("token_refresh"),
        {"refresh": refresh_token},
        format="json",
    )

    assert refresh_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "token" in str(refresh_resp.data["detail"]).lower()


def test_logout_revokes_session_and_blacklists_token(api_client):
    phone = "+573000001007"
    CustomUser.objects.create_user(
        phone_number=phone,
        password="Secret123!",
        first_name="Logout",
        is_verified=True,
    )
    login_resp = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "Secret123!"},
        format="json",
    )
    refresh_token = login_resp.data["refresh"]
    jti = str(RefreshToken(refresh_token)["jti"])

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")
    resp = api_client.post(reverse("logout"), {"refresh": refresh_token}, format="json")

    assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert not UserSession.objects.filter(refresh_token_jti=jti, is_active=True).exists()
    assert BlacklistedToken.objects.filter(token__jti=jti).exists()


def test_password_reset_flow_revokes_sessions(api_client, twilio_stub):
    phone = "+573000001008"
    user = CustomUser.objects.create_user(
        phone_number=phone,
        password="OldPass123!",
        first_name="Reset",
        is_verified=True,
    )
    twilio_stub.valid_codes = {"999999"}

    # Crear una sesión activa con login inicial
    login_resp = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "OldPass123!"},
        format="json",
    )
    assert login_resp.status_code == status.HTTP_200_OK
    assert UserSession.objects.filter(user=user, is_active=True).exists()

    request_resp = api_client.post(
        reverse("password_reset_request"),
        {"phone_number": phone},
        format="json",
    )
    assert request_resp.status_code == status.HTTP_200_OK

    confirm_resp = api_client.post(
        reverse("password_reset_confirm"),
        {"phone_number": phone, "code": "999999", "password": "NewPass123!"},
        format="json",
    )

    assert confirm_resp.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.check_password("NewPass123!")
    assert not UserSession.objects.filter(user=user, is_active=True).exists()

    # Login con contraseña nueva funciona, con la vieja falla
    old_login = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "OldPass123!"},
        format="json",
    )
    assert old_login.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST}

    new_login = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "NewPass123!"},
        format="json",
    )
    assert new_login.status_code == status.HTTP_200_OK


def test_change_password_requires_correct_current(api_client):
    phone = "+573000001009"
    user = CustomUser.objects.create_user(
        phone_number=phone,
        password="OldPass123!",
        first_name="Changer",
        is_verified=True,
    )
    login_resp = api_client.post(
        reverse("token_obtain_pair"),
        {"phone_number": phone, "password": "OldPass123!"},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    bad_resp = api_client.post(
        reverse("password_change"),
        {"old_password": "wrong", "new_password": "Another123!"},
        format="json",
    )
    assert bad_resp.status_code == status.HTTP_400_BAD_REQUEST

    good_resp = api_client.post(
        reverse("password_change"),
        {"old_password": "OldPass123!", "new_password": "Another123!"},
        format="json",
    )
    assert good_resp.status_code == status.HTTP_200_OK

    user.refresh_from_db()
    assert user.check_password("Another123!")
    assert not UserSession.objects.filter(user=user, is_active=True).exists()


def test_otp_verification_lockout_after_failed_attempts(api_client, twilio_stub):
    phone = "+573000001010"
    _register_user(api_client, phone=phone)
    twilio_stub.valid_codes = set()  # Siempre invalida

    for _ in range(3):
        resp = api_client.post(
            reverse("otp-confirm"),
            {"phone_number": phone, "code": "000000", "recaptcha_token": "token"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    lockout_resp = api_client.post(
        reverse("otp-confirm"),
        {"phone_number": phone, "code": "000000", "recaptcha_token": "token"},
        format="json",
    )

    assert lockout_resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "demasiados intentos" in str(lockout_resp.data["error"]).lower()
