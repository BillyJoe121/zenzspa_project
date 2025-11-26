from datetime import timedelta

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from profiles.middleware import KioskFlowEnforcementMiddleware
from profiles.models import ClinicalProfile, KioskSession
from users.models import CustomUser


class BaseKioskTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.api_client = APIClient()

        self.client_user = CustomUser.objects.create_user(
            phone_number="+573000000100",
            email="client@example.com",
            first_name="Cliente",
            password="Secret123!",
        )
        self.staff_user = CustomUser.objects.create_user(
            phone_number="+573000000200",
            email="staff@example.com",
            first_name="Staff",
            password="Secret123!",
            role=CustomUser.Role.STAFF,
            is_staff=True,
        )
        self.profile = ClinicalProfile.objects.create(user=self.client_user)
        self.session = KioskSession.objects.create(
            profile=self.profile,
            staff_member=self.staff_user,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def kiosk_headers(self):
        return {"HTTP_X_KIOSK_TOKEN": self.session.token}


class KioskFlowEnforcementMiddlewareTests(BaseKioskTestCase):
    @override_settings(KIOSK_ALLOWED_PATH_PREFIXES=("/api/v1/kiosk/",))
    def test_block_navigation_outside_whitelist(self):
        middleware = KioskFlowEnforcementMiddleware(lambda req: HttpResponse())
        request = self.factory.get("/api/v1/forbidden/", **self.kiosk_headers())

        response = middleware.process_view(request, lambda req, *a, **kw: HttpResponse(), (), {})

        self.assertEqual(response.status_code, 403)

    @override_settings(KIOSK_ALLOWED_PATH_PREFIXES=("/api/v1/kiosk/",))
    def test_allow_whitelisted_path(self):
        middleware = KioskFlowEnforcementMiddleware(lambda req: HttpResponse())
        request = self.factory.get("/api/v1/kiosk/heartbeat/", **self.kiosk_headers())

        response = middleware.process_view(request, lambda req, *a, **kw: HttpResponse(), (), {})

        self.assertIsNone(response)


class KioskSessionEndpointsTests(BaseKioskTestCase):
    def test_pending_changes_flow(self):
        url = reverse("kiosk-pending-changes")

        post_resp = self.api_client.post(url, **self.kiosk_headers())
        self.assertEqual(post_resp.status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.has_pending_changes)

        get_resp = self.api_client.get(url, **self.kiosk_headers())
        self.assertEqual(get_resp.status_code, 200)
        self.assertTrue(get_resp.data["has_pending_changes"])

        delete_resp = self.api_client.delete(url, **self.kiosk_headers())
        self.assertEqual(delete_resp.status_code, 200)
        self.session.refresh_from_db()
        self.assertFalse(self.session.has_pending_changes)

    def test_secure_screen_locks_session(self):
        self.session.expires_at = timezone.now() - timedelta(minutes=1)
        self.session.save(update_fields=["expires_at"])

        url = reverse("kiosk-secure-screen")
        response = self.api_client.post(url, **self.kiosk_headers())

        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.locked)
