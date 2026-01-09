import logging

from django.utils import timezone
from django.db.models import Q
from rest_framework import status

from core.utils.exceptions import BusinessLogicError
from core.models import GlobalSettings
from ..models import Appointment, WaitlistEntry

logger = logging.getLogger(__name__)


class WaitlistService:
    DEFAULT_TTL_MINUTES = 60

    @classmethod
    def recycle_expired_offers(cls):
        now = timezone.now()
        expired = WaitlistEntry.objects.filter(
            status=WaitlistEntry.Status.OFFERED,
            offer_expires_at__lt=now,
        )
        for entry in expired:
            entry.reset_offer()

    @classmethod
    def offer_slot_for_appointment(cls, appointment):
        if appointment is None:
            return

        cls.recycle_expired_offers()
        if not getattr(GlobalSettings.load(), "waitlist_enabled", False):
            return

        service_ids = list(appointment.services.values_list('id', flat=True))
        queryset = WaitlistEntry.objects.filter(
            status=WaitlistEntry.Status.WAITING,
            desired_date=appointment.start_time.date(),
        )
        if service_ids:
            queryset = queryset.filter(
                Q(services__isnull=True) | Q(services__in=service_ids)
            )

        entry = queryset.order_by('created_at').distinct().first()
        if not entry:
            return

        entry.mark_offered(appointment, cls._ttl_minutes())

    @classmethod
    def ensure_enabled(cls):
        settings = GlobalSettings.load()
        if not getattr(settings, "waitlist_enabled", False):
            raise BusinessLogicError(
                detail="La lista de espera está deshabilitada.",
                internal_code="APP-009",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    @classmethod
    def _ttl_minutes(cls):
        minutes = getattr(GlobalSettings.load(), "waitlist_ttl_minutes", None)
        if not minutes or minutes <= 0:
            return cls.DEFAULT_TTL_MINUTES
        return minutes

