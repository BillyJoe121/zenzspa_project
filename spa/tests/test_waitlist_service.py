import pytest
from datetime import timedelta
from django.utils import timezone
from model_bakery import baker

from spa.services import WaitlistService
from spa.models import Appointment, WaitlistEntry, Service, ServiceCategory
from core.exceptions import BusinessLogicError


@pytest.mark.django_db
def test_waitlist_offer_slot_sets_offer(mocker):
    # habilitar waitlist
    settings_mock = mocker.Mock(waitlist_enabled=True)
    mocker.patch("spa.services.waitlist.GlobalSettings.load", return_value=settings_mock)
    mocker.patch("spa.tasks.notify_waitlist_availability.delay", return_value=None)

    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category)
    appointment = baker.make(
        Appointment,
        start_time=timezone.now() + timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1, hours=1),
    )
    appointment.services.add(service)

    entry = baker.make(
        WaitlistEntry,
        status=WaitlistEntry.Status.WAITING,
        desired_date=appointment.start_time.date(),
    )

    WaitlistService.offer_slot_for_appointment(appointment)
    entry.refresh_from_db()

    assert entry.status == WaitlistEntry.Status.OFFERED
    assert entry.offered_appointment == appointment
    assert entry.offer_expires_at is not None


@pytest.mark.django_db
def test_waitlist_ensure_enabled_raises_when_disabled(mocker):
    settings_mock = mocker.Mock(waitlist_enabled=False)
    mocker.patch("spa.services.waitlist.GlobalSettings.load", return_value=settings_mock)

    with pytest.raises(BusinessLogicError):
        WaitlistService.ensure_enabled()
