from rest_framework import serializers

from ..models import Package, PackageService, UserPackage, Voucher
from .appointment import ServiceSerializer


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


class VoucherSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    is_redeemable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Voucher
        fields = [
            'id', 'code', 'service_name', 'status', 'is_redeemable', 'expires_at'
        ]


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

