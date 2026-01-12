from rest_framework import permissions, viewsets

from users.permissions import IsAdminUser
from ..models import Package
from ..serializers.package import AdminPackageSerializer


class AdminPackageViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para paquetes de servicios."""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = AdminPackageSerializer
    queryset = Package.objects.prefetch_related('packageservice_set__service').order_by('-created_at')

    http_method_names = ["get", "post", "put", "patch", "delete"]
