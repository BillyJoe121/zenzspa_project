from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import WaitlistEntry
from ..serializers import WaitlistConfirmSerializer, WaitlistJoinSerializer
from ..services import WaitlistService

# Note: Waitlist actions remain within AppointmentViewSet; this module can host future waitlist-specific endpoints.

