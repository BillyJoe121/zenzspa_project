from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from ..models import Appointment
from ..serializers.appointment import AppointmentSerializer

class ClientAppointmentHistoryView(generics.ListAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Appointment.objects.filter(user=self.request.user).order_by('-start_time')
