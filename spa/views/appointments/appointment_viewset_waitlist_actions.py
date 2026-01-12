"""
Acciones de lista de espera para citas.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsVerified

from ...models import Service, WaitlistEntry
from ...serializers import (
    WaitlistConfirmSerializer,
    WaitlistJoinSerializer,
)
from ...services import WaitlistService


class AppointmentWaitlistActionsMixin:
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsVerified], url_path='waitlist/join')
    def waitlist_join(self, request):
        """Unirse a la lista de espera."""
        WaitlistService.ensure_enabled()
        serializer = WaitlistJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service_ids = serializer.validated_data.get('service_ids') or []
        services = Service.objects.filter(id__in=service_ids, is_active=True)
        if service_ids and services.count() != len(set(service_ids)):
            return Response({'error': 'Alguno de los servicios no existe o está inactivo.'}, status=422)

        entry = WaitlistEntry.objects.create(
            user=request.user,
            desired_date=serializer.validated_data['desired_date'],
            notes=serializer.validated_data.get('notes', ''),
        )
        if services:
            entry.services.set(services)
        response = {
            'id': str(entry.id),
            'status': entry.status,
            'desired_date': entry.desired_date,
        }
        return Response(response, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[IsAuthenticated, IsVerified],
        url_path=r'waitlist/(?P<waitlist_id>[0-9a-fA-F-]+)/confirm',
    )
    def waitlist_confirm(self, request, waitlist_id=None):
        """Confirma o rechaza una oferta de la lista de espera."""
        WaitlistService.ensure_enabled()
        with transaction.atomic():
            entry = get_object_or_404(
                WaitlistEntry.objects.select_for_update(),
                id=waitlist_id,
                user=request.user,
            )
            serializer = WaitlistConfirmSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            accept = serializer.validated_data['accept']

            if entry.status != WaitlistEntry.Status.OFFERED:
                return Response({'error': 'La lista de espera no tiene una oferta activa.'}, status=400)

            now = timezone.now()
            if entry.offer_expires_at and now > entry.offer_expires_at:
                entry.status = WaitlistEntry.Status.EXPIRED
                entry.save(update_fields=['status', 'updated_at'])
                WaitlistService.offer_slot_for_appointment(entry.offered_appointment)
                return Response({'error': 'La oferta ya no está disponible.'}, status=409)

            if not accept:
                entry.reset_offer()
                WaitlistService.offer_slot_for_appointment(entry.offered_appointment)
                return Response({'detail': 'Has rechazado el turno. Avisaremos al siguiente cliente.'}, status=status.HTTP_200_OK)

            entry.status = WaitlistEntry.Status.CONFIRMED
            entry.save(update_fields=['status', 'updated_at'])
        return Response({'detail': 'Has confirmado el turno disponible.'}, status=status.HTTP_200_OK)
