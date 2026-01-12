import pytest
from datetime import timedelta
from django.utils import timezone
from model_bakery import baker

from spa.models import WaitlistEntry, Appointment, AppointmentItem, ServiceCategory, Service


@pytest.mark.django_db
def test_waitlist_mark_and_reset_offer():
    category = baker.make(ServiceCategory)
    service = baker.make(Service, category=category)
    appt = baker.make(
        Appointment,
        start_time=timezone.now() + timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1, hours=1),
    )
    AppointmentItem.objects.create(
        appointment=appt,
        service=service,
        duration=service.duration,
        price_at_purchase=service.price
    )
    entry = baker.make(WaitlistEntry, status=WaitlistEntry.Status.WAITING)

    entry.mark_offered(appt, ttl_minutes=30)
    entry.refresh_from_db()
    assert entry.status == WaitlistEntry.Status.OFFERED
    assert entry.offered_appointment == appt
    assert entry.offer_expires_at is not None

    entry.reset_offer()
    entry.refresh_from_db()
    assert entry.status == WaitlistEntry.Status.WAITING
    assert entry.offered_appointment is None
