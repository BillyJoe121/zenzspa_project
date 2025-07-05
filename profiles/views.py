# Crea el archivo zenzspa_project/profiles/views.py con este contenido

from rest_framework import generics
from django.shortcuts import get_object_or_404
from .models import UserProfile
from .serializers import UserProfileSerializer
from .permissions import IsStaffOrAdmin
from users.models import CustomUser


class UserProfileDetailView(generics.RetrieveUpdateAPIView):
    """
    Vista para ver y actualizar el perfil clínico de un usuario.
    Accesible solo por STAFF y ADMIN.
    """
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsStaffOrAdmin]
    lookup_field = 'user__phone_number'
    lookup_url_kwarg = 'phone_number'

    def get_object(self):
        # Usamos el phone_number de la URL para encontrar el usuario y su perfil.
        phone_number = self.kwargs[self.lookup_url_kwarg]
        user = get_object_or_404(CustomUser, phone_number=phone_number)
        return get_object_or_404(UserProfile, user=user)
