from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from users.permissions import IsAdminUser
from users.models import CustomUser
from ..models import Voucher, Service
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

    @action(detail=False, methods=['get'], url_path='client/(?P<client_id>[^/.]+)/available')
    def client_available_vouchers(self, request, client_id=None):
        """
        Lista los vouchers disponibles de un cliente específico.
        
        GET /api/v1/admin/vouchers/client/{client_id}/available/
        
        Query params:
            - service_id: Filtrar por servicio específico (opcional)
        
        Returns:
            Lista de vouchers disponibles agrupados por servicio.
        """
        # Validar que el cliente existe
        client = get_object_or_404(
            CustomUser,
            id=client_id,
            role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
            is_active=True,
            is_persona_non_grata=False
        )
        
        # Obtener vouchers disponibles
        vouchers = Voucher.objects.filter(
            user=client,
            status=Voucher.VoucherStatus.AVAILABLE,
        ).select_related('service', 'user_package__package')
        
        # Filtrar por servicio si se especifica
        service_id = request.query_params.get('service_id')
        if service_id:
            vouchers = vouchers.filter(service_id=service_id)
        
        # Excluir vouchers expirados
        today = timezone.now().date()
        vouchers = vouchers.filter(
            expires_at__gte=today
        ) | vouchers.filter(expires_at__isnull=True)
        
        # Serializar
        serializer = self.get_serializer(vouchers, many=True)
        
        # Agrupar por servicio
        grouped = {}
        for voucher_data in serializer.data:
            service_id = voucher_data.get('service', {}).get('id')
            service_name = voucher_data.get('service', {}).get('name', 'Sin servicio')
            
            if service_id not in grouped:
                grouped[service_id] = {
                    'service_id': service_id,
                    'service_name': service_name,
                    'vouchers': []
                }
            grouped[service_id]['vouchers'].append(voucher_data)
        
        return Response({
            'client_id': str(client.id),
            'client_name': client.get_full_name() or client.first_name or client.phone_number,
            'vouchers_by_service': list(grouped.values()),
            'total_available': vouchers.count()
        })

    @action(detail=False, methods=['post'], url_path='create-manual')
    def create_manual_voucher(self, request):
        """
        Crea un voucher manual para un cliente.
        
        POST /api/v1/admin/vouchers/create-manual/
        
        Body:
        {
            "client_id": "uuid",
            "service_id": "uuid",
            "expires_at": "2025-12-31" (opcional, por defecto 90 días)
        }
        
        Returns:
            El voucher creado.
        """
        client_id = request.data.get('client_id')
        service_id = request.data.get('service_id')
        expires_at = request.data.get('expires_at')
        
        # Validaciones
        if not client_id or not service_id:
            return Response(
                {'error': 'client_id y service_id son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar cliente
        try:
            client = CustomUser.objects.get(
                id=client_id,
                role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
                is_active=True,
                is_persona_non_grata=False
            )
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Cliente no encontrado o inactivo.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validar servicio
        try:
            service = Service.objects.get(id=service_id, is_active=True)
        except Service.DoesNotExist:
            return Response(
                {'error': 'Servicio no encontrado o inactivo.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calcular fecha de expiración
        if not expires_at:
            expires_at = timezone.now().date() + timedelta(days=90)
        
        # Crear voucher
        voucher = Voucher.objects.create(
            user=client,
            service=service,
            expires_at=expires_at,
            status=Voucher.VoucherStatus.AVAILABLE
        )
        
        # Registrar en audit log
        from core.models import AuditLog
        AuditLog.objects.create(
            admin_user=request.user,
            target_user=client,
            action=AuditLog.Action.VOUCHER_CREATED,
            details=f"Admin '{request.user.first_name}' creó voucher manual {voucher.code} para servicio {service.name}"
        )
        
        serializer = self.get_serializer(voucher)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

