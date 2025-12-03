import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from profiles.models import (
    ClinicalProfile,
    ClientDoshaAnswer,
    ConsentDocument,
    ConsentTemplate,
    Dosha,
    DoshaOption,
    DoshaQuestion,
    KioskSession,
    LocalizedPain,
)
from users.models import CustomUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client_user():
    user = CustomUser.objects.create_user(
        phone_number="+573200000001",
        password="Secret123!",
        first_name="Cliente",
        last_name="Ejemplo",
        email="cliente@example.com",
        is_verified=True,
    )
    profile = ClinicalProfile.objects.create(
        user=user,
        dosha=Dosha.VATA,
        activity_level=ClinicalProfile.ActivityLevel.MODERATE,
    )
    return user, profile


@pytest.fixture
def staff_user():
    return CustomUser.objects.create_user(
        phone_number="+573200000099",
        password="Staff123!",
        first_name="Staff",
        role=CustomUser.Role.STAFF,
        is_staff=True,
        is_verified=True,
    )


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def test_profile_view_me_includes_pains_and_consents(api_client, client_user):
    user, profile = client_user
    pain = LocalizedPain.objects.create(
        profile=profile,
        body_part=LocalizedPain.BodyPart.LOWER_BACK,
        pain_level=LocalizedPain.PainLevel.MODERATE,
        periodicity=LocalizedPain.PainPeriodicity.OCCASIONAL,
        notes="Empeora al estar sentado",
    )
    template = ConsentTemplate.objects.create(version=1, title="Consent v1", body="texto legal", is_active=True)
    consent = ConsentDocument.objects.create(profile=profile, template=template, is_signed=True, ip_address="1.1.1.1")

    _auth(api_client, user)
    url = reverse("clinical-profile-me")
    resp = api_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert data["user"]["phone_number"] == user.phone_number
    assert data["dosha"] == profile.dosha
    assert data["activity_level"] == profile.activity_level
    assert any(p["body_part"] == pain.body_part for p in data["pains"])
    assert any(c["id"] == str(consent.id) for c in data["consents"])


def test_profile_update_records_history(api_client, client_user):
    user, profile = client_user
    before_history = profile.history.count()

    _auth(api_client, user)
    url = reverse("clinical-profile-me")
    payload = {
        "diet_type": ClinicalProfile.Diet.VEGAN,
        "sleep_quality": ClinicalProfile.SleepQuality.POOR,
        "medical_conditions": "Diabetes Tipo 2",
    }
    resp = api_client.patch(url, payload, format="json")

    assert resp.status_code == status.HTTP_200_OK
    profile.refresh_from_db()
    assert profile.diet_type == ClinicalProfile.Diet.VEGAN
    assert profile.sleep_quality == ClinicalProfile.SleepQuality.POOR
    assert "Diabetes" in profile.medical_conditions
    assert profile.history.count() > before_history


def test_add_localized_pain(api_client, client_user):
    user, profile = client_user
    _auth(api_client, user)
    url = reverse("clinical-profile-me")

    resp = api_client.patch(
        url,
        {
            "pains": [
                {
                    "body_part": LocalizedPain.BodyPart.LOWER_BACK,
                    "pain_level": LocalizedPain.PainLevel.MODERATE,
                    "periodicity": LocalizedPain.PainPeriodicity.OCCASIONAL,
                    "notes": "Empeora al estar sentado",
                }
            ]
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    profile.refresh_from_db()
    pains = list(profile.pains.all())
    assert len(pains) == 1
    assert pains[0].body_part == LocalizedPain.BodyPart.LOWER_BACK


def test_complete_dosha_quiz_updates_profile(api_client, client_user):
    user, profile = client_user
    q1 = DoshaQuestion.objects.create(text="Pregunta 1", category="Physical")
    q2 = DoshaQuestion.objects.create(text="Pregunta 2", category="Mind")
    o1 = DoshaOption.objects.create(question=q1, text="O1", associated_dosha=Dosha.VATA, weight=2)
    o2 = DoshaOption.objects.create(question=q2, text="O2", associated_dosha=Dosha.VATA, weight=1)

    _auth(api_client, user)
    url = reverse("dosha-quiz-submit")
    resp = api_client.post(
        url,
        {
            "answers": [
                {"question_id": str(q1.id), "selected_option_id": str(o1.id)},
                {"question_id": str(q2.id), "selected_option_id": str(o2.id)},
            ]
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    profile.refresh_from_db()
    assert profile.dosha == Dosha.VATA
    assert profile.element == ClinicalProfile.Element.AIR
    assert ClientDoshaAnswer.objects.filter(profile=profile).count() == 2


def test_incomplete_dosha_quiz_returns_error(api_client, client_user):
    user, profile = client_user
    q1 = DoshaQuestion.objects.create(text="Pregunta 1", category="Physical")
    q2 = DoshaQuestion.objects.create(text="Pregunta 2", category="Mind")
    o1 = DoshaOption.objects.create(question=q1, text="O1", associated_dosha=Dosha.VATA, weight=1)
    o2 = DoshaOption.objects.create(question=q2, text="O2", associated_dosha=Dosha.PITTA, weight=1)

    _auth(api_client, user)
    url = reverse("dosha-quiz-submit")
    resp = api_client.post(
        url,
        {
            "answers": [
                {"question_id": str(q1.id), "selected_option_id": str(o1.id)},
            ]
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "QUIZ_INCOMPLETE" == resp.data.get("code")
    profile.refresh_from_db()
    assert profile.dosha == Dosha.VATA  # Sin cambios adicionales
    assert ClientDoshaAnswer.objects.filter(profile=profile).count() == 0


def test_sign_consent_and_prevent_duplicate(api_client, client_user, settings):
    settings.TRUST_PROXY = True
    user, profile = client_user
    template = ConsentTemplate.objects.create(version=1, title="Consent", body="texto legal", is_active=True)
    _auth(api_client, user)
    url = reverse("sign-consent")
    resp = api_client.post(
        url,
        {"template_id": str(template.id)},
        format="json",
        HTTP_X_FORWARDED_FOR="10.0.0.1",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    consent = ConsentDocument.objects.get(profile=profile, template_version=template.version)
    assert consent.signature_hash
    assert consent.ip_address == "10.0.0.1"

    dup_resp = api_client.post(url, {"template_id": str(template.id)}, format="json")
    assert dup_resp.status_code == status.HTTP_409_CONFLICT


def test_export_clinical_data(api_client, client_user):
    user, profile = client_user
    LocalizedPain.objects.create(
        profile=profile,
        body_part=LocalizedPain.BodyPart.NECK,
        pain_level=LocalizedPain.PainLevel.LOW,
        periodicity=LocalizedPain.PainPeriodicity.SPECIFIC,
    )
    template = ConsentTemplate.objects.create(version=1, title="Consent", body="texto legal", is_active=True)
    ConsentDocument.objects.create(profile=profile, template=template, is_signed=True)

    _auth(api_client, user)
    url = reverse("export-clinical-data")
    resp = api_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert data["user"]["phone_number"] == user.phone_number
    assert data["profile"]["dosha"] == profile.dosha
    assert len(data["pains"]) == 1
    assert len(data["consents"]) == 1


def test_kiosk_start_session_creates_token(api_client, client_user, staff_user):
    user, profile = client_user
    staff = staff_user

    _auth(api_client, staff)
    url = reverse("kiosk-start-session")
    resp = api_client.post(url, {"client_phone_number": user.phone_number}, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    token = resp.data["kiosk_token"]
    session = KioskSession.objects.get(token=token)
    assert session.profile == profile
    assert session.staff_member == staff


def test_kiosk_client_completes_quiz(api_client, client_user, staff_user):
    user, profile = client_user
    staff = staff_user
    session = KioskSession.objects.create(
        profile=profile,
        staff_member=staff,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    q = DoshaQuestion.objects.create(text="Kiosk Q1", category="Physical")
    o = DoshaOption.objects.create(question=q, text="O1", associated_dosha=Dosha.KAPHA, weight=3)

    url = reverse("dosha-quiz-submit")
    resp = api_client.post(
        url,
        {"answers": [{"question_id": str(q.id), "selected_option_id": str(o.id)}]},
        format="json",
        HTTP_X_KIOSK_TOKEN=session.token,
    )

    assert resp.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert session.status == KioskSession.Status.COMPLETED
    profile.refresh_from_db()
    assert profile.dosha == Dosha.KAPHA


def test_kiosk_heartbeat_expired_locks_session(api_client, client_user, staff_user):
    user, profile = client_user
    staff = staff_user
    session = KioskSession.objects.create(
        profile=profile,
        staff_member=staff,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    url = reverse("kiosk-heartbeat")
    resp = api_client.post(url, format="json", HTTP_X_KIOSK_TOKEN=session.token)

    assert resp.status_code == 440
    session.refresh_from_db()
    assert session.status == KioskSession.Status.LOCKED


def test_kiosk_heartbeat_keeps_session_active(api_client, client_user, staff_user):
    user, profile = client_user
    staff = staff_user
    session = KioskSession.objects.create(
        profile=profile,
        staff_member=staff,
        expires_at=timezone.now() + timedelta(minutes=2),
    )
    last_activity = session.last_activity

    url = reverse("kiosk-heartbeat")
    resp = api_client.post(url, format="json", HTTP_X_KIOSK_TOKEN=session.token)

    assert resp.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert session.status == KioskSession.Status.ACTIVE
    assert session.last_activity >= last_activity


def test_kiosk_pending_changes_discard(api_client, client_user, staff_user):
    user, profile = client_user
    staff = staff_user
    session = KioskSession.objects.create(
        profile=profile,
        staff_member=staff,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    pending_url = reverse("kiosk-pending-changes")
    mark_resp = api_client.post(pending_url, format="json", HTTP_X_KIOSK_TOKEN=session.token)
    assert mark_resp.status_code == status.HTTP_200_OK

    discard_url = reverse("kiosk-discard")
    discard_resp = api_client.post(discard_url, format="json", HTTP_X_KIOSK_TOKEN=session.token)
    assert discard_resp.status_code == status.HTTP_200_OK

    session.refresh_from_db()
    assert session.status == KioskSession.Status.LOCKED
    assert session.has_pending_changes is False
