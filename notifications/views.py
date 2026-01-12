from rest_framework import generics, permissions
from rest_framework.response import Response

from .models import NotificationPreference
from .serializers import NotificationPreferenceSerializer


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return NotificationPreference.for_user(self.request.user)

    def get(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)
