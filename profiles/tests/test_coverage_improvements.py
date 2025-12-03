import pytest
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from model_bakery import baker
from unittest.mock import patch

from profiles.models import (
    ClinicalProfile, LocalizedPain, DoshaQuestion,
    DoshaOption, ConsentTemplate, ConsentDocument, KioskSession, ClientDoshaAnswer,
    Dosha
)
from users.models import CustomUser
from core.models import AuditLog
from spa.models import Appointment

@pytest.mark.django_db
class TestClinicalProfileViewSetMe(TestCase):
    """Tests for ClinicalProfileViewSet.me action"""

    def setUp(self):
        self.client = APIClient()
        self.user = baker.make(CustomUser, phone_number="+573001111111", is_verified=True)
        self.profile = ClinicalProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

    def test_me_retrieve(self):
        """Test retrieving own profile via /me/"""
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['phone_number'], self.user.phone_number)

    def test_me_update(self):
        """Test updating own profile via /me/"""
        response = self.client.patch(
            '/api/v1/users/me/',
            {'diet_type': ClinicalProfile.Diet.VEGETARIAN},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.diet_type, ClinicalProfile.Diet.VEGETARIAN)

    def test_me_unauthenticated(self):
        """Test /me/ without authentication"""
        self.client.logout()
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, 401)


@pytest.mark.django_db
class TestRevokeConsentView(TestCase):
    """Tests for RevokeConsentView"""

    def setUp(self):
        self.client = APIClient()
        self.user = baker.make(CustomUser, phone_number="+573001111111", is_verified=True)
        self.profile = ClinicalProfile.objects.create(user=self.user)
        self.template = ConsentTemplate.objects.create(version=1, title="T", body="B")
        self.consent = ConsentDocument.objects.create(
            profile=self.profile,
            template=self.template,
            is_signed=True,
            signed_at=timezone.now()
        )
        self.client.force_authenticate(user=self.user)

    def test_revoke_own_consent(self):
        """Test user revoking their own consent"""
        response = self.client.post(
            f'/api/v1/consents/revoke/{self.consent.id}/',
            {'reason': 'Changed mind'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.consent.refresh_from_db()
        self.assertFalse(self.consent.is_signed)
        self.assertEqual(self.consent.revoked_reason, 'Changed mind')
        self.assertIsNotNone(self.consent.revoked_at)

    def test_revoke_others_consent_as_user_fails(self):
        """Test user cannot revoke another's consent"""
        other_user = baker.make(CustomUser, phone_number="+573002222222")
        other_profile = ClinicalProfile.objects.create(user=other_user)
        other_consent = ConsentDocument.objects.create(
            profile=other_profile,
            template=self.template,
            is_signed=True
        )
        
        response = self.client.post(
            f'/api/v1/consents/revoke/{other_consent.id}/',
            {'reason': 'Malicious'},
            format='json'
        )
        self.assertEqual(response.status_code, 403)

    def test_revoke_as_staff(self):
        """Test staff can revoke any consent"""
        staff = baker.make(CustomUser, role=CustomUser.Role.STAFF, is_staff=True)
        self.client.force_authenticate(user=staff)
        
        response = self.client.post(
            f'/api/v1/consents/revoke/{self.consent.id}/',
            {'reason': 'Staff revocation'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.consent.refresh_from_db()
        self.assertFalse(self.consent.is_signed)
        self.assertEqual(self.consent.revoked_by, staff)

    def test_revoke_already_revoked(self):
        """Test revoking an already revoked consent fails"""
        self.consent.is_signed = False
        self.consent.save()
        
        response = self.client.post(
            f'/api/v1/consents/revoke/{self.consent.id}/',
            {'reason': 'Again'},
            format='json'
        )
        self.assertEqual(response.status_code, 400)


@pytest.mark.django_db
class TestClinicalProfileHistoryViewSet(TestCase):
    """Tests for ClinicalProfileHistoryViewSet"""

    def setUp(self):
        self.client = APIClient()
        self.staff = baker.make(CustomUser, role=CustomUser.Role.STAFF, is_staff=True)
        self.user = baker.make(CustomUser, phone_number="+573001111111")
        self.profile = ClinicalProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.staff)

    def test_history_list(self):
        """Test listing history"""
        self.profile.dosha = Dosha.VATA
        self.profile.save()
        
        response = self.client.get('/api/v1/clinical-history/')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data['results']), 0)

    def test_history_filter_by_profile_id(self):
        """Test filtering history by profile_id"""
        response = self.client.get(f'/api/v1/clinical-history/?profile_id={self.profile.id}')
        self.assertEqual(response.status_code, 200)

    def test_history_filter_by_user_id(self):
        """Test filtering history by user_id"""
        response = self.client.get(f'/api/v1/clinical-history/?user_id={self.user.id}')
        self.assertEqual(response.status_code, 200)


@pytest.mark.django_db
class TestKioskSessionViews(TestCase):
    """Tests for KioskSession views"""

    def setUp(self):
        self.client = APIClient()
        self.staff = baker.make(CustomUser, role=CustomUser.Role.STAFF, is_staff=True)
        self.user = baker.make(CustomUser, phone_number="+573001111111")
        self.profile = ClinicalProfile.objects.create(user=self.user)
        self.session = KioskSession.objects.create(
            profile=self.profile,
            staff_member=self.staff,
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.client.credentials(HTTP_X_KIOSK_TOKEN=self.session.token)

    def test_lock_session(self):
        """Test locking session"""
        response = self.client.post('/api/v1/kiosk/lock/')
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.locked)

    def test_discard_changes(self):
        """Test discarding changes"""
        self.session.mark_pending_changes()
        response = self.client.post('/api/v1/kiosk/discard/')
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertFalse(self.session.has_pending_changes)
        self.assertEqual(self.session.status, KioskSession.Status.LOCKED)

    def test_heartbeat_expired(self):
        """Test heartbeat on expired session returns 440"""
        self.session.expires_at = timezone.now() - timedelta(minutes=1)
        self.session.save()
        
        response = self.client.post('/api/v1/kiosk/heartbeat/')
        self.assertEqual(response.status_code, 440)
        self.session.refresh_from_db()
        self.assertTrue(self.session.locked)

    def test_secure_screen_view(self):
        """Test secure screen view"""
        response = self.client.post('/api/v1/kiosk/secure-screen/')
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.locked)


@pytest.mark.django_db
class TestDoshaQuizSubmitStandardMode(TestCase):
    """Tests for DoshaQuizSubmitView in standard mode"""

    def setUp(self):
        self.client = APIClient()
        self.user = baker.make(CustomUser, phone_number="+573001111111", is_verified=True)
        self.profile = ClinicalProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)
        self.question = DoshaQuestion.objects.create(text="Q1")
        self.option = DoshaOption.objects.create(question=self.question, text="O1", associated_dosha='VATA', weight=1)

    def test_submit_quiz_standard_user(self):
        """Test submitting quiz as authenticated user"""
        data = {
            "answers": [
                {"question_id": str(self.question.id), "selected_option_id": str(self.option.id)}
            ]
        }
        response = self.client.post('/api/v1/dosha-quiz/submit/', data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ClientDoshaAnswer.objects.filter(profile=self.profile).exists())


# --- SERIALIZER TESTS ---

from profiles.serializers import (
    LocalizedPainSerializer,
    ClinicalProfileSerializer,
    DoshaQuestionSerializer,
    KioskSessionStatusSerializer,
    ClinicalProfileHistorySerializer
)

@pytest.mark.django_db
class TestSerializerCoverage(TestCase):
    """Tests for Serializers coverage"""

    def setUp(self):
        self.user = baker.make(CustomUser, phone_number="+573001111111")
        self.profile = ClinicalProfile.objects.create(user=self.user)

    def test_localized_pain_invalid_body_part(self):
        """Test validation for invalid body part"""
        serializer = LocalizedPainSerializer(data={
            'body_part': 'INVALID',
            'pain_level': LocalizedPain.PainLevel.LOW,
            'periodicity': LocalizedPain.PainPeriodicity.CONSTANT
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('body_part', serializer.errors)

    def test_clinical_profile_update_nested_pains(self):
        """Test updating profile with nested pains"""
        pain1 = LocalizedPain.objects.create(
            profile=self.profile,
            body_part=LocalizedPain.BodyPart.HEAD,
            pain_level=LocalizedPain.PainLevel.LOW,
            periodicity=LocalizedPain.PainPeriodicity.CONSTANT
        )
        
        data = {
            'pains': [
                # Update existing
                {'id': str(pain1.id), 'body_part': LocalizedPain.BodyPart.HEAD, 'pain_level': LocalizedPain.PainLevel.HIGH},
                # Create new
                {'body_part': LocalizedPain.BodyPart.UPPER_BACK, 'pain_level': LocalizedPain.PainLevel.MODERATE, 'periodicity': LocalizedPain.PainPeriodicity.OCCASIONAL}
            ]
        }
        
        serializer = ClinicalProfileSerializer(instance=self.profile, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.pains.count(), 2)
        pain1.refresh_from_db()
        self.assertEqual(pain1.pain_level, LocalizedPain.PainLevel.HIGH)

    def test_dosha_question_nested_options(self):
        """Test create/update DoshaQuestion with nested options"""
        # Create
        data = {
            'text': 'New Question',
            'category': 'Physical',
            'options': [
                {'text': 'Opt 1', 'associated_dosha': 'VATA', 'weight': 1},
                {'text': 'Opt 2', 'associated_dosha': 'PITTA', 'weight': 2}
            ]
        }
        serializer = DoshaQuestionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        question = serializer.save()
        self.assertEqual(question.options.count(), 2)

        # Update
        update_data = {
            'text': 'Updated Question',
            'options': [
                # Update existing
                {'id': question.options.first().id, 'text': 'Updated Opt 1', 'associated_dosha': 'VATA', 'weight': 1},
                # Create new
                {'text': 'Opt 3', 'associated_dosha': 'KAPHA', 'weight': 3}
                # Delete second option (by omission)
            ]
        }
        serializer = DoshaQuestionSerializer(instance=question, data=update_data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        
        question.refresh_from_db()
        self.assertEqual(question.text, 'Updated Question')
        self.assertEqual(question.options.count(), 2)
        self.assertTrue(question.options.filter(text='Updated Opt 1').exists())
        self.assertTrue(question.options.filter(text='Opt 3').exists())

    def test_kiosk_session_status_serializer(self):
        """Test computed fields in KioskSessionStatusSerializer"""
        staff = baker.make(CustomUser, role=CustomUser.Role.STAFF, is_staff=True)
        session = KioskSession.objects.create(
            profile=self.profile,
            staff_member=staff,
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        
        serializer = KioskSessionStatusSerializer(session)
        data = serializer.data
        
        self.assertIn('expired', data)
        self.assertIn('secure_screen_url', data)
        self.assertIn('force_secure_screen', data)
        self.assertIn('remaining_seconds', data)

    def test_clinical_profile_history_serializer(self):
        """Test computed fields in ClinicalProfileHistorySerializer"""
        # Create history
        self.profile.dosha = Dosha.VATA
        self.profile.save()
        
        history = self.profile.history.first()
        serializer = ClinicalProfileHistorySerializer(history)
        data = serializer.data
        
        self.assertIn('changed_by', data)
        self.assertIn('delta', data)
        self.assertIn('profile_id', data)

@pytest.mark.django_db
class TestAdditionalCoverage(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = baker.make(CustomUser, role=CustomUser.Role.ADMIN, is_staff=True, is_superuser=True, is_verified=True)
        self.staff = baker.make(CustomUser, role=CustomUser.Role.STAFF, is_staff=True, is_verified=True)
        self.user = baker.make(CustomUser, phone_number='+573009999999', is_verified=True)
        self.profile = ClinicalProfile.objects.create(user=self.user)

    def test_anonymize_profile_view(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('clinical-profile-anonymize', kwargs={'phone_number': self.user.phone_number})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_number.startswith('ANON-'))

    def test_kiosk_start_session_client_not_found(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse('kiosk-start-session')
        
        # We need to pass a valid phone number to pass serializer validation
        # but mock the get call to raise DoesNotExist to hit the view's error handling
        with patch('users.models.CustomUser.objects.get', side_effect=CustomUser.DoesNotExist):
            response = self.client.post(url, {'client_phone_number': self.user.phone_number})
            self.assertEqual(response.status_code, 404)

    def test_kiosk_session_status_view(self):
        session = KioskSession.objects.create(
            profile=self.profile,
            staff_member=self.staff,
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.client.credentials(HTTP_X_KIOSK_TOKEN=session.token)
        url = reverse('kiosk-status')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'ACTIVE')

    def test_kiosk_session_heartbeat_success(self):
        session = KioskSession.objects.create(
            profile=self.profile,
            staff_member=self.staff,
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.client.credentials(HTTP_X_KIOSK_TOKEN=session.token)
        url = reverse('kiosk-heartbeat')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['detail'], 'Heartbeat registrado.')

    def test_dosha_quiz_submit_kiosk_mode(self):
        session = KioskSession.objects.create(
            profile=self.profile,
            staff_member=self.staff,
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        q1 = DoshaQuestion.objects.create(text="Q1", category="Physical")
        o1 = DoshaOption.objects.create(question=q1, text="O1", associated_dosha=Dosha.VATA, weight=1)
        
        self.client.credentials(HTTP_X_KIOSK_TOKEN=session.token)
        url = reverse('dosha-quiz-submit')
        data = {
            'answers': [
                {'question_id': q1.id, 'selected_option_id': o1.id}
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, KioskSession.Status.COMPLETED)

    def test_clinical_profile_viewset_admin_queryset(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('clinical-profile-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Admin sees all
        self.assertGreaterEqual(len(response.data['results']), 1)

    def test_clinical_profile_viewset_staff_no_allowed_users(self):
        self.client.force_authenticate(user=self.staff)
        # No appointments created for this staff
        url = reverse('clinical-profile-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_clinical_profile_update_audit_log(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('clinical-profile-detail', kwargs={'phone_number': self.user.phone_number})
        data = {'medical_conditions': 'New Condition'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)

