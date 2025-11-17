from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .models import BlockedPhoneNumber
from .serializers import SimpleUserSerializer, UserRegistrationSerializer


CustomUser = get_user_model()


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
        self.assertEqual(data["email"], "o***r@example.com")

    def test_own_profile_is_not_masked(self):
        data = self._serialize(self.target)
        self.assertEqual(data["phone_number"], self.target.phone_number)
        self.assertEqual(data["email"], self.target.email)

    def test_anonymous_user_is_masked(self):
        data = self._serialize(AnonymousUser())
        self.assertEqual(data["phone_number"], "+57****67")
        self.assertEqual(data["email"], "o***r@example.com")


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
