import pytest
from datetime import timedelta
from django.utils import timezone
from model_bakery import baker

from spa.tasks import cleanup_old_appointments
from spa.models import Appointment


@pytest.mark.django_db
def test_cleanup_old_appointments_removes_only_old():
    old_date = timezone.now() - timedelta(days=800)
    recent_date = timezone.now() - timedelta(days=10)

    old_appt = baker.make(
        Appointment,
        status=Appointment.AppointmentStatus.COMPLETED,
    )
    Appointment.objects.filter(id=old_appt.id).update(updated_at=old_date)

    recent_appt = baker.make(
        Appointment,
        status=Appointment.AppointmentStatus.CANCELLED,
    )
    Appointment.objects.filter(id=recent_appt.id).update(updated_at=recent_date)

    result = cleanup_old_appointments(days_to_keep=730)

    assert result["deleted"] == 1
    assert Appointment.objects.filter(id=old_appt.id).count() == 0
    assert Appointment.objects.filter(id=recent_appt.id).count() == 1
