from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from core.exceptions import BusinessLogicError
from spa.models import StaffAvailability
from users.permissions import (
    IsAdminUser,
    IsClient,
    IsStaff,
    IsStaffOrAdmin,
    IsVerified,
    IsVIP,
)
from users.signals import user_session_logged_in
from users.models import BlockedPhoneNumber, CustomUser, UserSession
from users.serializers import (
    CustomTokenObtainPairSerializer,
    SessionAwareTokenRefreshSerializer,
    SimpleUserSerializer,
    UserRegistrationSerializer,
)
from users.services import SimpleCircuitBreaker, TwilioService, verify_recaptcha
from users.tasks import cleanup_inactive_sessions, send_non_grata_alert_to_admins
from users.utils import get_client_ip, get_request_metadata, register_user_session
from users.views import (
    BlockIPView,
    ChangePasswordView,
    FlagNonGrataView,
    LogoutAllView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    StaffListView,
    UserRegistrationView,
    UserSessionDeleteView,
    UserSessionListView,
    VerifySMSView,
)



class SimpleUserSerializerMaskingTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.target = CustomUser.objects.create_user(
            phone_number="+573001234567",
            email="target@example.com",
            first_name="Objetivo",
            password="Secret123!",
        )
        self.staff_user = CustomUser.objects.create_user(
            phone_number="+573000000001",
            email="staff@example.com",
            first_name="Staff",
            password="Secret123!",
            role=CustomUser.Role.STAFF,
            is_staff=True,
        )
        self.admin_user = CustomUser.objects.create_user(
            phone_number="+573000000002",
            email="admin@example.com",
            first_name="Admin",
            password="Secret123!",
            role=CustomUser.Role.ADMIN,
            is_staff=True,
        )
        self.other_client = CustomUser.objects.create_user(
            phone_number="+573000000003",
            email="other@example.com",
            first_name="Cliente",
            password="Secret123!",
        )

    def _serialize(self, viewer):
        request = self.factory.get("/api/users/")
        request.user = viewer
        serializer = SimpleUserSerializer(self.target, context={"request": request})
        return serializer.data

    def test_staff_sees_unmasked_data(self):
        data = self._serialize(self.staff_user)
        self.assertEqual(data["phone_number"], self.target.phone_number)
        self.assertEqual(data["email"], self.target.email)

    def test_admin_inherits_staff_visibility(self):
        data = self._serialize(self.admin_user)
        self.assertEqual(data["phone_number"], self.target.phone_number)
        self.assertEqual(data["email"], self.target.email)

    def test_client_sees_masked_data(self):
        data = self._serialize(self.other_client)
        self.assertEqual(data["phone_number"], "+57****67")
        self.assertEqual(data["email"], "t***t@example.com")

    def test_own_profile_is_not_masked(self):
        data = self._serialize(self.target)
        self.assertEqual(data["phone_number"], self.target.phone_number)
        self.assertEqual(data["email"], self.target.email)

    def test_anonymous_user_is_masked(self):
        data = self._serialize(AnonymousUser())
        self.assertEqual(data["phone_number"], "+57****67")
        self.assertEqual(data["email"], "t***t@example.com")


class UserRegistrationSerializerTests(TestCase):
    def setUp(self):
        self.base_payload = {
            "phone_number": "+573001111111",
            "email": "newuser@example.com",
            "first_name": "Nuevo",
            "last_name": "Usuario",
            "password": "Secret123!",
        }

    def _get_serializer(self, payload=None):
        data = payload or self.base_payload.copy()
        return UserRegistrationSerializer(data=data)

    @patch("users.serializers.send_non_grata_alert_to_admins.delay")
    def test_non_grata_phone_from_blocklist_is_rejected(self, mock_delay):
        BlockedPhoneNumber.objects.create(phone_number=self.base_payload["phone_number"], notes="CNG")
        serializer = self._get_serializer()
        self.assertFalse(serializer.is_valid())
        self.assertIn("bloqueado", serializer.errors["phone_number"][0])
        mock_delay.assert_called_once_with(self.base_payload["phone_number"])

    @patch("users.serializers.send_non_grata_alert_to_admins.delay")
    def test_existing_non_grata_user_is_rejected(self, mock_delay):
        user = CustomUser.objects.create_user(
            phone_number=self.base_payload["phone_number"],
            email="blocked@example.com",
            first_name="Bloqueado",
            password="Secret123!",
        )
        user.is_persona_non_grata = True
        user.save(update_fields=["is_persona_non_grata"])

        serializer = self._get_serializer()
        self.assertFalse(serializer.is_valid())
        self.assertIn("bloqueado", serializer.errors["phone_number"][0])
        mock_delay.assert_called_once_with(self.base_payload["phone_number"])

    @patch("users.serializers.send_non_grata_alert_to_admins.delay")
    def test_existing_regular_user_is_rejected_with_specific_message(self, mock_delay):
        CustomUser.objects.create_user(
            phone_number=self.base_payload["phone_number"],
            email="regular@example.com",
            first_name="Regular",
            password="Secret123!",
        )
        serializer = self._get_serializer()
        self.assertFalse(serializer.is_valid())
        self.assertIn("ya existe", serializer.errors["phone_number"][0])
        mock_delay.assert_not_called()


class UserRegistrationViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = UserRegistrationView.as_view()
        self.payload = {
            "phone_number": "+573002222222",
            "email": "viewreg@example.com",
            "first_name": "View",
            "last_name": "Reg",
            "password": "Secret123!",
        }

    @patch("users.views._requires_recaptcha", return_value=True)
    @patch("users.views.verify_recaptcha", return_value=False)
    def test_registration_requires_recaptcha(self, mock_recaptcha, mock_requires):
        request = self.factory.post("/register/", self.payload, format="json")
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomUser.objects.filter(phone_number=self.payload["phone_number"]).exists())

    @patch("users.views.TwilioService")
    @patch("users.views._requires_recaptcha", return_value=False)
    def test_registration_twilio_failure_rolls_back(self, mock_requires, mock_twilio):
        mock_twilio.return_value.send_verification_code.side_effect = BusinessLogicError("Twilio down")
        request = self.factory.post("/register/", self.payload, format="json")
        response = self.view(request)
        self.assertIn(response.status_code, (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_503_SERVICE_UNAVAILABLE))
        self.assertFalse(CustomUser.objects.filter(phone_number=self.payload["phone_number"]).exists())


class VerifySMSRateLimitTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = VerifySMSView.as_view()
        self.user = CustomUser.objects.create_user(
            phone_number="+573009999999",
            email="otp@example.com",
            first_name="OTP",
            password="Secret123!",
            is_verified=False,
        )
        self.original_ip_limit = VerifySMSView.MAX_IP_ATTEMPTS
        self.original_global_limit = VerifySMSView.MAX_GLOBAL_ATTEMPTS
        cache.clear()

    def tearDown(self):
        VerifySMSView.MAX_IP_ATTEMPTS = self.original_ip_limit
        VerifySMSView.MAX_GLOBAL_ATTEMPTS = self.original_global_limit
        cache.clear()

    def _perform_request(self):
        payload = {"phone_number": self.user.phone_number, "code": "000000"}
        request = self.factory.post("/verify/", payload, format="json")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        return self.view(request)

    @patch("users.views.TwilioService")
    def test_ip_rate_limit_blocks_after_threshold(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = False
        VerifySMSView.MAX_IP_ATTEMPTS = 1

        response1 = self._perform_request()
        self.assertEqual(response1.status_code, status.HTTP_400_BAD_REQUEST)

        response2 = self._perform_request()
        self.assertEqual(response2.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response2.data["code"], "OTP_IP_LOCKED")

    @patch("users.views.TwilioService")
    def test_global_rate_limit_blocks_service(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = False
        VerifySMSView.MAX_GLOBAL_ATTEMPTS = 1
        VerifySMSView.MAX_IP_ATTEMPTS = 999

        response1 = self._perform_request()
        self.assertEqual(response1.status_code, status.HTTP_400_BAD_REQUEST)

        response2 = self._perform_request()
        self.assertEqual(response2.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response2.data["code"], "OTP_GLOBAL_LIMIT")

    @patch("users.views.TwilioService")
    def test_verify_sms_success_returns_tokens(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = True
        VerifySMSView.MAX_IP_ATTEMPTS = 999
        request = self.factory.post(
            "/verify/",
            {"phone_number": self.user.phone_number, "code": "123456"},
            format="json",
        )
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("refresh", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)


class VerifySMSAdditionalTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = VerifySMSView.as_view()
        self.user = CustomUser.objects.create_user(
            phone_number="+573001111112",
            email="otp2@example.com",
            first_name="OTP2",
            password="Secret123!",
            is_verified=False,
        )

    def tearDown(self):
        cache.clear()

    def _post(self, extra=None):
        payload = {"phone_number": self.user.phone_number, "code": "000000"}
        if extra:
            payload.update(extra)
        request = self.factory.post("/verify/", payload, format="json")
        request.META["REMOTE_ADDR"] = "9.9.9.9"
        return self.view(request)

    def test_lockout_returns_429(self):
        cache.set(f"otp_lockout_{self.user.phone_number}", True, timeout=600)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch("users.views._requires_recaptcha", return_value=True)
    def test_recaptcha_required_returns_400(self, mock_requires):
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("users.views.TwilioService")
    def test_invalid_code_increments_attempts(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = False
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        attempts = cache.get(f"otp_attempts_{self.user.phone_number}")
        self.assertEqual(attempts, 1)

    def test_blocked_ip_returns_403(self):
        cache.set("blocked_ip:9.9.9.9", True, timeout=60)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="token", TWILIO_VERIFY_SERVICE_SID="VSID")
class TwilioCircuitBreakerTests(TestCase):
    def setUp(self):
        client_patcher = patch("users.services.Client")
        self.mock_client_cls = client_patcher.start()
        self.addCleanup(client_patcher.stop)
        self.mock_client = MagicMock()
        self.mock_client_cls.return_value = self.mock_client
        self.service = TwilioService()

    def _build_dummy_client(self, side_effect=None):
        class DummyVerifications:
            def __init__(self, effect):
                self.effect = effect

            def create(self, **kwargs):
                if self.effect:
                    raise self.effect
                return SimpleNamespace(status="approved")

        class DummyVerificationChecks(DummyVerifications):
            pass

        class DummyService:
            def __init__(self, effect):
                self.verifications = DummyVerifications(effect)
                self.verification_checks = DummyVerificationChecks(effect)

        class DummyVerifyRoot:
            def __init__(self, effect):
                self._service = DummyService(effect)

            @property
            def v2(self):
                return self

            def services(self, sid):
                return self._service

        dummy = MagicMock()
        dummy.verify = DummyVerifyRoot(side_effect)
        return dummy

    def test_circuit_breaker_blocks_after_failures(self):
        breaker = SimpleCircuitBreaker(failure_threshold=1, recovery_timeout=60)
        with patch("users.services.twilio_breaker", breaker):
            self.service.client = self._build_dummy_client(side_effect=RuntimeError("boom"))
            with self.assertRaises(BusinessLogicError) as first_error:
                self.service.send_verification_code("+573001234567")
            self.assertEqual(first_error.exception.detail["code"], "USER-TWILIO-UNAVAILABLE")

            with self.assertRaises(BusinessLogicError) as second_error:
                self.service.send_verification_code("+573001234567")
        self.assertEqual(second_error.exception.detail["code"], "USER-TWILIO-BLOCKED")


@override_settings(TWILIO_ACCOUNT_SID="AC123", TWILIO_AUTH_TOKEN="token", TWILIO_VERIFY_SERVICE_SID="VSID")
class TwilioServiceSuccessTests(TestCase):
    def setUp(self):
        client_patcher = patch("users.services.Client")
        self.mock_client_cls = client_patcher.start()
        self.addCleanup(client_patcher.stop)

    def test_send_and_check_verification_code(self):
        service = TwilioService()

        class DummyVerification:
            status = "pending"

        class DummyVerificationCheck:
            status = "approved"

        class DummyService:
            def verifications(self):
                return self

        def _verifications_create(*args, **kwargs):
            return DummyVerification()

        def _checks_create(*args, **kwargs):
            return DummyVerificationCheck()

        dummy = MagicMock()
        dummy.verify.v2.services.return_value.verifications.create.side_effect = _verifications_create
        dummy.verify.v2.services.return_value.verification_checks.create.side_effect = _checks_create
        service.client = dummy

        status_value = service.send_verification_code("+573009999998")
        self.assertEqual(status_value, "pending")
        self.assertTrue(service.check_verification_code("+573009999998", "123456"))


class RecaptchaVerificationTests(TestCase):
    def _mock_response(self, data, success=True, status_code=200):
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.status_code = status_code
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @override_settings(RECAPTCHA_V3_SECRET_KEY="secret")
    @patch("users.services.requests.post")
    def test_verify_recaptcha_success(self, mock_post):
        mock_post.return_value = self._mock_response({"success": True, "score": 0.9, "action": "auth__otp_request"})
        self.assertTrue(verify_recaptcha("token", remote_ip="1.1.1.1", action="auth__otp_request"))

    @override_settings(RECAPTCHA_V3_SECRET_KEY="secret")
    @patch("users.services.requests.post")
    def test_verify_recaptcha_failure_due_to_action(self, mock_post):
        mock_post.return_value = self._mock_response({"success": True, "score": 0.9, "action": "different"})
        self.assertFalse(verify_recaptcha("token", action="auth__otp_request"))

    @override_settings(RECAPTCHA_V3_SECRET_KEY="secret")
    @patch("users.services.requests.post")
    def test_verify_recaptcha_failure_low_score(self, mock_post):
        mock_post.return_value = self._mock_response({"success": True, "score": 0.2, "action": "auth__otp_request"})
        self.assertFalse(verify_recaptcha("token", action="auth__otp_request", min_score=0.8))


class SignalTests(TestCase):
    def test_staff_creation_creates_default_availability(self):
        user = CustomUser.objects.create_user(
            phone_number="+573004200000",
            email="staff@example.com",
            first_name="Staffer",
            password="Secret123!",
            role=CustomUser.Role.STAFF,
            is_staff=True,
        )
        slots = StaffAvailability.objects.filter(staff_member=user)
        self.assertEqual(slots.count(), 12)

    def test_user_session_logged_in_creates_and_updates_session(self):
        user = CustomUser.objects.create_user(
            phone_number="+573004200001",
            email="session@example.com",
            first_name="SessionUser",
            password="Secret123!",
            is_verified=True,
        )
        user_session_logged_in.send(
            sender=self.__class__,
            user=user,
            refresh_token_jti="abc",
            ip_address="1.1.1.1",
            user_agent="agent",
        )
        session = UserSession.objects.get(refresh_token_jti="abc")
        self.assertEqual(session.ip_address, "1.1.1.1")

        user_session_logged_in.send(
            sender=self.__class__,
            user=user,
            refresh_token_jti="abc",
            ip_address="2.2.2.2",
            user_agent="agent2",
        )
        session.refresh_from_db()
        self.assertEqual(session.ip_address, "2.2.2.2")

    @patch("users.signals.safe_audit_log")
    def test_audit_role_change_emits_log(self, mock_audit):
        user = CustomUser.objects.create_user(
            phone_number="+573004200010",
            email="role@example.com",
            first_name="Role",
            password="Secret123!",
            role=CustomUser.Role.CLIENT,
        )
        user.role = CustomUser.Role.ADMIN
        user.save(update_fields=["role"])
        mock_audit.assert_called()


@override_settings(DEFAULT_FROM_EMAIL="alerts@example.com")
class TaskTests(TestCase):
    @patch("users.tasks.send_mail")
    def test_send_non_grata_alert_sends_email(self, mock_send_mail):
        CustomUser.objects.create_user(
            phone_number="+573004300000",
            email="admin@example.com",
            first_name="Admin",
            password="Secret123!",
            role=CustomUser.Role.ADMIN,
            is_staff=True,
            is_active=True,
        )
        result = send_non_grata_alert_to_admins("+573004300001")
        self.assertIn("+573004300001", result)
        mock_send_mail.assert_called_once()


class UtilsTests(TestCase):
    def test_get_client_ip_prefers_forwarded(self):
        request = SimpleNamespace(META={"HTTP_X_FORWARDED_FOR": "10.0.0.1, 172.16.0.1", "REMOTE_ADDR": "127.0.0.1"})
        self.assertEqual(get_client_ip(request), "10.0.0.1")
        request = SimpleNamespace(META={"REMOTE_ADDR": "127.0.0.2"})
        self.assertEqual(get_client_ip(request), "127.0.0.2")

    def test_get_request_metadata_truncates_user_agent(self):
        ua = "x" * 600
        request = SimpleNamespace(META={"REMOTE_ADDR": "127.0.0.3", "HTTP_USER_AGENT": ua})
        ip, agent = get_request_metadata(request)
        self.assertEqual(ip, "127.0.0.3")
        self.assertEqual(len(agent), 512)

    def test_register_user_session_emits_signal(self):
        received = {}

        def receiver(sender, **kwargs):
            received.update(kwargs)

        user_session_logged_in.connect(receiver, weak=False)
        user = CustomUser.objects.create_user(
            phone_number="+573004400000",
            email="signal@example.com",
            first_name="Signal",
            password="Secret123!",
            is_verified=True,
        )
        request = SimpleNamespace(META={"REMOTE_ADDR": "1.1.1.1", "HTTP_USER_AGENT": "agent"})
        register_user_session(user, "jti-123", request=request, sender=self.__class__)
        self.assertEqual(received["refresh_token_jti"], "jti-123")
        self.assertEqual(received["ip_address"], "1.1.1.1")


class UrlsTests(TestCase):
    def test_urls_resolve(self):
        from users import urls

        self.assertGreater(len(urls.urlpatterns), 0)


class AdminBlockIPTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = CustomUser.objects.create_user(
            phone_number="+573005000000",
            email="adminblock@example.com",
            first_name="AdminBlock",
            password="Secret123!",
            role=CustomUser.Role.ADMIN,
            is_staff=True,
        )

    def test_block_ip_endpoint_sets_cache(self):
        view = BlockIPView.as_view()
        request = self.factory.post("/admin/block-ip/", {"ip": "5.5.5.5", "ttl": 100}, format="json")
        force_authenticate(request, user=self.admin)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(cache.get("blocked_ip:5.5.5.5"))


class ViewsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = CustomUser.objects.create_user(
            phone_number="+573004500000",
            email="viewer@example.com",
            first_name="View",
            password="Secret123!",
            is_verified=True,
        )

    @patch("users.views._requires_recaptcha", return_value=False)
    @patch("users.views.TwilioService")
    def test_password_reset_request_sends_code(self, mock_twilio, mock_requires):
        view = PasswordResetRequestView.as_view()
        request = self.factory.post("/password-reset/request/", {"phone_number": self.user.phone_number}, format="json")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_twilio.return_value.send_verification_code.assert_called_once_with(self.user.phone_number)

    @patch("users.views._requires_recaptcha", return_value=True)
    @patch("users.views.verify_recaptcha", return_value=False)
    def test_password_reset_request_requires_recaptcha(self, mock_verify, mock_requires):
        view = PasswordResetRequestView.as_view()
        request = self.factory.post("/password-reset/request/", {"phone_number": self.user.phone_number}, format="json")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("users.views.TwilioService")
    def test_password_reset_confirm_updates_password(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = True
        view = PasswordResetConfirmView.as_view()
        payload = {"phone_number": self.user.phone_number, "code": "123456", "password": "NewSecret123!"}
        request = self.factory.post("/password-reset/confirm/", payload, format="json")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(CustomUser.objects.get(pk=self.user.pk).check_password("NewSecret123!"))

    @patch("users.views.TwilioService")
    def test_password_reset_confirm_rejects_invalid_code(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = False
        view = PasswordResetConfirmView.as_view()
        payload = {"phone_number": self.user.phone_number, "code": "123456", "password": "NewSecret123!"}
        request = self.factory.post("/password-reset/confirm/", payload, format="json")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("users.views.TwilioService")
    def test_password_reset_confirm_user_not_found(self, mock_twilio):
        mock_twilio.return_value.check_verification_code.return_value = True
        view = PasswordResetConfirmView.as_view()
        payload = {"phone_number": "+573009999000", "code": "123456", "password": "NewSecret123!"}
        request = self.factory.post("/password-reset/confirm/", payload, format="json")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_logout_view_requires_refresh(self):
        view = LogoutView.as_view()
        request = self.factory.post("/logout/", {}, format="json")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_view_blacklists_token(self):
        refresh = RefreshToken.for_user(self.user)
        view = LogoutView.as_view()
        request = self.factory.post("/logout/", {"refresh": str(refresh)}, format="json")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_logout_view_handles_invalid_token(self):
        view = LogoutView.as_view()
        request = self.factory.post("/logout/", {"refresh": "invalid"}, format="json")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_view(self):
        view = ChangePasswordView.as_view()
        payload = {"old_password": "Secret123!", "new_password": "NewSecret123!"}
        request = self.factory.post("/password/change/", payload, format="json")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecret123!"))

    @patch("users.views._revoke_all_sessions")
    def test_logout_all_view(self, mock_revoke):
        view = LogoutAllView.as_view()
        request = self.factory.post("/logout_all/", {}, format="json")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_revoke.assert_called_once_with(self.user)

    def test_user_session_list_view_returns_sessions(self):
        UserSession.objects.create(user=self.user, refresh_token_jti="abc")
        view = UserSessionListView.as_view()
        request = self.factory.get("/sessions/")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = response.data["count"] if isinstance(response.data, dict) and "count" in response.data else len(response.data)
        self.assertEqual(count, 1)

    def test_user_session_delete_view_marks_inactive(self):
        session = UserSession.objects.create(user=self.user, refresh_token_jti="abc")
        view = UserSessionDeleteView.as_view()
        request = self.factory.delete("/sessions/{}/".format(session.id))
        force_authenticate(request, user=self.user)
        response = view(request, id=str(session.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        session.refresh_from_db()
        self.assertFalse(session.is_active)

    def test_staff_list_view_returns_only_staff(self):
        staff = CustomUser.objects.create_user(
            phone_number="+573004500010",
            email="stafflist@example.com",
            first_name="Staffer",
            password="Secret123!",
            role=CustomUser.Role.STAFF,
            is_staff=True,
        )
        view = StaffListView.as_view()
        request = self.factory.get("/staff/")
        admin = CustomUser.objects.create_user(
            phone_number="+573004500011",
            email="adminlist@example.com",
            first_name="Admin",
            password="Secret123!",
            role=CustomUser.Role.ADMIN,
            is_staff=True,
        )
        force_authenticate(request, user=admin)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["results"] if isinstance(response.data, dict) and "results" in response.data else response.data
        self.assertIn(str(staff.id), {item["id"] for item in data})

    @patch("users.views.NotificationService.send_notification")
    @patch("users.views.AdminNotification.objects.create")
    @patch("users.views.AuditLog.objects.create")
    @patch("users.views.Appointment.objects")
    def test_flag_non_grata_view_marks_user(self, mock_appointments, mock_audit, mock_admin_notification, mock_notify):
        admin = CustomUser.objects.create_user(
            phone_number="+573004500001",
            email="admin2@example.com",
            first_name="Admin",
            password="Secret123!",
            role=CustomUser.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        target = CustomUser.objects.create_user(
            phone_number="+573004500002",
            email="victim@example.com",
            first_name="Victim",
            password="Secret123!",
            is_verified=True,
        )
        mock_appointments.filter.return_value.update.return_value = 1
        view = FlagNonGrataView.as_view()
        request = self.factory.patch("/flag/{}/".format(target.phone_number), {"internal_notes": "spam"})
        force_authenticate(request, user=admin)
        response = view(request, phone_number=target.phone_number)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target.refresh_from_db()
        self.assertTrue(target.is_persona_non_grata)
        mock_audit.assert_called_once()
        mock_admin_notification.assert_called_once()
        mock_notify.assert_called_once()


class SessionAwareTokenRefreshSerializerTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = CustomUser.objects.create_user(
            phone_number="+573004444444",
            email="refresh@example.com",
            first_name="Refresh",
            password="Secret123!",
            is_verified=True,
        )

    def test_refresh_updates_session_jti(self):
        refresh = RefreshToken.for_user(self.user)
        session = UserSession.objects.create(
            user=self.user,
            refresh_token_jti=str(refresh["jti"]),
            ip_address="1.1.1.1",
        )
        serializer = SessionAwareTokenRefreshSerializer(
            data={"refresh": str(refresh)},
            context={"request": self.factory.post("/token/refresh/")},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        session.refresh_from_db()
        self.assertEqual(session.refresh_token_jti, str(RefreshToken(data["refresh"])["jti"]))

    def test_refresh_without_session_fails(self):
        refresh = RefreshToken.for_user(self.user)
        serializer = SessionAwareTokenRefreshSerializer(
            data={"refresh": str(refresh)},
            context={"request": self.factory.post("/token/refresh/")},
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class CleanupInactiveSessionsTaskTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            phone_number="+573005555555",
            email="sessions@example.com",
            first_name="Session",
            password="Secret123!",
            is_verified=True,
        )

    def test_cleanup_inactive_sessions_removes_old_records(self):
        recent = UserSession.objects.create(user=self.user, refresh_token_jti="recent")
        old_session = UserSession.objects.create(user=self.user, refresh_token_jti="old", is_active=True)
        inactive = UserSession.objects.create(user=self.user, refresh_token_jti="inactive", is_active=False)

        UserSession.objects.filter(pk=old_session.pk).update(
            last_activity=timezone.now() - timedelta(days=60)
        )

        result = cleanup_inactive_sessions()
        self.assertGreaterEqual(result["deleted_count"], 2)
        self.assertTrue(UserSession.objects.filter(pk=recent.pk).exists())


class CustomUserPhoneValidationTests(TestCase):
    def test_invalid_phone_number_is_rejected(self):
        user = CustomUser(
            phone_number="3001234567",
            email="invalid@example.com",
            first_name="Invalid",
        )
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_valid_phone_number_passes(self):
        user = CustomUser(
            phone_number="+573006666666",
            email="valid@example.com",
            first_name="Valid",
        )
        user.set_password("Secret123!")
        user.full_clean()  # No exception raised


class CustomUserManagerTests(TestCase):
    def test_create_user_requires_phone_and_email(self):
        with self.assertRaises(ValueError):
            CustomUser.objects.create_user(
                phone_number="",
                email=None,
                first_name="X",
                password="Secret123!",
            )

    def test_create_superuser_sets_required_flags(self):
        admin = CustomUser.objects.create_superuser(
            phone_number="+573007777778",
            email="super@example.com",
            first_name="Admin",
            password="Secret123!",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_verified)
        with self.assertRaises(ValueError):
            CustomUser.objects.create_superuser(
                phone_number="+573007777779",
                email="bad@example.com",
                first_name="Bad",
                password="Secret123!",
                is_staff=False,
            )


class CustomUserBehaviorTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            phone_number="+573008888880",
            email="vip@example.com",
            first_name="VIP",
            password="Secret123!",
        )

    def test_is_vip_property(self):
        self.user.role = CustomUser.Role.VIP
        self.user.vip_expires_at = timezone.now().date() + timedelta(days=1)
        self.assertTrue(self.user.is_vip)
        self.user.vip_expires_at = timezone.now().date() - timedelta(days=1)
        self.assertFalse(self.user.is_vip)

    @patch("spa.models.Payment")
    @patch("spa.models.Appointment")
    def test_has_pending_final_payment_checks_appointments(self, mock_appt, mock_payment):
        mock_appt.objects.filter.return_value.exists.return_value = True
        mock_payment.objects.filter.return_value.exists.return_value = False
        self.assertTrue(self.user.has_pending_final_payment())
        mock_appt.objects.filter.return_value.exists.return_value = False
        mock_payment.objects.filter.return_value.exists.return_value = False
        self.assertFalse(self.user.has_pending_final_payment())


class PermissionClassesTests(TestCase):
    def setUp(self):
        self.request = SimpleNamespace()
        self.request.user = SimpleNamespace(
            is_authenticated=True,
            is_verified=True,
            role=CustomUser.Role.ADMIN,
        )

    def test_is_verified(self):
        perm = IsVerified()
        self.assertTrue(perm.has_permission(self.request, None))
        self.request.user.is_verified = False
        self.assertFalse(perm.has_permission(self.request, None))

    def test_role_permissions(self):
        perms = [
            (IsClient(), CustomUser.Role.CLIENT),
            (IsVIP(), CustomUser.Role.VIP),
            (IsStaff(), CustomUser.Role.STAFF),
            (IsAdminUser(), CustomUser.Role.ADMIN),
        ]
        for perm, role in perms:
            self.request.user.role = role
            self.assertTrue(perm.has_permission(self.request, None))
        staff_admin = IsStaffOrAdmin()
        self.request.user.role = CustomUser.Role.STAFF
        self.assertTrue(staff_admin.has_permission(self.request, None))
        self.request.user.role = CustomUser.Role.CLIENT
        self.assertFalse(staff_admin.has_permission(self.request, None))


class CustomTokenSerializerTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = CustomUser.objects.create_user(
            phone_number="+573009000000",
            email="token@example.com",
            first_name="Token",
            password="Secret123!",
            is_verified=False,
        )

    def test_obtain_pair_requires_verified_user(self):
        request = self.factory.post("/api/token/")
        serializer = CustomTokenObtainPairSerializer(
            data={"phone_number": self.user.phone_number, "password": "Secret123!"},
            context={"request": request},
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    @patch("users.serializers.register_user_session")
    def test_obtain_pair_registers_session_when_verified(self, mock_register):
        self.user.is_verified = True
        self.user.save(update_fields=["is_verified"])
        request = self.factory.post("/api/token/")
        serializer = CustomTokenObtainPairSerializer(
            data={"phone_number": self.user.phone_number, "password": "Secret123!"},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.assertIn("refresh", data)
        mock_register.assert_called_once()
