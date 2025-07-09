from rest_framework import generics
from django.shortcuts import get_object_or_404
# --- INICIO DE LA MODIFICACIÓN ---
from .models import ClinicalProfile # Se actualiza la importación del modelo
from .serializers import ClinicalProfileSerializer # Se actualiza la importación del serializador
# --- FIN DE LA MODIFICACIÓN ---
from .permissions import IsStaffOrAdmin
from users.models import CustomUser


# --- INICIO DE LA MODIFICACIÓN ---
# Se renombra la vista para mantener la consistencia
class ClinicalProfileDetailView(generics.RetrieveUpdateAPIView):
# --- FIN DE LA MODIFICACIÓN ---
    """
    Vista para ver y actualizar el perfil clínico de un usuario.
    Accesible solo por STAFF y ADMIN.
    """
    # Se actualiza el queryset y el serializer_class
    queryset = ClinicalProfile.objects.all().select_related('user').prefetch_related('pains')
    serializer_class = ClinicalProfileSerializer
    permission_classes = [IsStaffOrAdmin]
    lookup_field = 'user__phone_number'
    lookup_url_kwarg = 'phone_number'

    def get_object(self):
        phone_number = self.kwargs[self.lookup_url_kwarg]
        user = get_object_or_404(CustomUser, phone_number=phone_number)
        # Se actualiza la búsqueda para usar el nuevo modelo
        return get_object_or_404(ClinicalProfile, user=user)