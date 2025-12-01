from rest_framework import serializers

from ..models import Package, PackageService, Service, UserPackage, Voucher
from .appointment import ServiceSerializer
from users.models import CustomUser


class PackageServiceSerializer(serializers.ModelSerializer):
    service = ServiceSerializer(read_only=True)

    class Meta:
        model = PackageService
        fields = ['service', 'quantity']


class PackageSerializer(serializers.ModelSerializer):
    services = PackageServiceSerializer(source='packageservice_set', many=True, read_only=True)

    class Meta:
        model = Package
        fields = ['id', 'name', 'description', 'price',
                  'grants_vip_months', 'is_active', 'services', 'validity_days']


class AdminPackageServiceSerializer(serializers.ModelSerializer):
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all())

    class Meta:
        model = PackageService
        fields = ['service', 'quantity']


class AdminPackageSerializer(serializers.ModelSerializer):
    services = AdminPackageServiceSerializer(many=True, required=False)

    class Meta:
        model = Package
        fields = [
            'id',
            'name',
            'description',
            'price',
            'grants_vip_months',
            'is_active',
            'validity_days',
            'services',
        ]

    def _sync_services(self, package, services_data):
        if services_data is None:
            return
        current = {ps.service_id: ps for ps in PackageService.objects.filter(package=package)}
        seen = set()
        for service_entry in services_data:
            service = service_entry['service']
            quantity = service_entry.get('quantity', 1)
            seen.add(service.id)
            if service.id in current:
                ps = current[service.id]
                if ps.quantity != quantity:
                    ps.quantity = quantity
                    ps.save(update_fields=['quantity'])
            else:
                PackageService.objects.create(package=package, service=service, quantity=quantity)
        # Remove services not in payload
        to_delete = [ps_id for ps_id in current if ps_id not in seen]
        if to_delete:
            PackageService.objects.filter(package=package, service_id__in=to_delete).delete()

    def create(self, validated_data):
        services_data = validated_data.pop('services', [])
        package = super().create(validated_data)
        self._sync_services(package, services_data)
        return package

    def update(self, instance, validated_data):
        services_data = validated_data.pop('services', None)
        package = super().update(instance, validated_data)
        self._sync_services(package, services_data)
        return package


class VoucherSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    is_redeemable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Voucher
        fields = [
            'id', 'code', 'service_name', 'status', 'is_redeemable', 'expires_at'
        ]


class AdminVoucherSerializer(serializers.ModelSerializer):
    """Serializer para CRUD administrativo de vouchers."""
    user = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all())

    class Meta:
        model = Voucher
        fields = [
            'id',
            'user',
            'service',
            'user_package',
            'code',
            'status',
            'expires_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        user = attrs.get('user') or getattr(self.instance, 'user', None)
        user_package = attrs.get('user_package') or getattr(self.instance, 'user_package', None)
        if user_package and user_package.user != user:
            raise serializers.ValidationError("El paquete pertenece a otro usuario.")
        return attrs

    def create(self, validated_data):
        # Permitir omitir code; el modelo lo generará.
        return super().create(validated_data)


class UserPackageDetailSerializer(serializers.ModelSerializer):
    package = PackageSerializer(read_only=True)
    vouchers = VoucherSerializer(many=True, read_only=True)

    class Meta:
        model = UserPackage
        fields = [
            'id', 'package', 'purchase_date', 'expires_at', 'vouchers'
        ]


class PackagePurchaseCreateSerializer(serializers.Serializer):
    package_id = serializers.PrimaryKeyRelatedField(
        queryset=Package.objects.filter(is_active=True),
        source="package",
        write_only=True,
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        return validated_data
