from rest_framework import permissions, viewsets

from users.permissions import IsAdminUser
from ..models import Voucher
from ..serializers.package import AdminVoucherSerializer


class AdminVoucherViewSet(viewsets.ModelViewSet):
    """
    CRUD administrativo para vouchers.
    Permite crear, editar estado/fecha de expiración y eliminar vouchers emitidos.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = AdminVoucherSerializer
    queryset = Voucher.objects.select_related("user", "service", "user_package__package").order_by("expires_at")

    http_method_names = ["get", "post", "put", "patch", "delete"]
