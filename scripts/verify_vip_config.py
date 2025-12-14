#!/usr/bin/env python
"""
Script para verificar la configuración VIP y endpoints de la API.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from decimal import Decimal
from core.models.settings import GlobalSettings
from spa.models import Service


def verify_vip_configuration():
    """Verifica que la configuración VIP esté correcta."""

    print("=" * 70)
    print("VERIFICACIÓN DE CONFIGURACIÓN VIP")
    print("=" * 70)

    # 1. Verificar configuración global
    print("\n1. CONFIGURACIÓN GLOBAL")
    print("-" * 70)
    settings = GlobalSettings.load()

    print(f"   Precio VIP Mensual: ${settings.vip_monthly_price} COP")
    print(f"   Meses para Lealtad: {settings.loyalty_months_required} meses")

    if settings.loyalty_voucher_service:
        print(f"   Servicio de Recompensa: {settings.loyalty_voucher_service.name}")
    else:
        print(f"   Servicio de Recompensa: No configurado")

    print(f"   Días de Expiración de Créditos: {settings.credit_expiration_days} días")

    # Validaciones
    issues = []

    if settings.vip_monthly_price <= 0:
        issues.append("⚠️  Precio VIP es $0 o negativo")

    if settings.loyalty_months_required < 1:
        issues.append("⚠️  Meses para lealtad debe ser al menos 1")

    if not settings.loyalty_voucher_service:
        issues.append("⚠️  No hay servicio configurado para recompensas de lealtad")

    # 2. Verificar servicios con precio VIP
    print("\n2. SERVICIOS CON PRECIO VIP")
    print("-" * 70)

    services_with_vip = Service.objects.filter(
        is_active=True,
        vip_price__isnull=False
    ).order_by('name')

    services_without_vip = Service.objects.filter(
        is_active=True,
        vip_price__isnull=True
    ).order_by('name')

    print(f"   Servicios con precio VIP: {services_with_vip.count()}")
    print(f"   Servicios sin precio VIP: {services_without_vip.count()}")

    if services_with_vip.exists():
        print("\n   Ejemplos de precios VIP:")
        for service in services_with_vip[:5]:
            discount_pct = ((service.price - service.vip_price) / service.price * 100)
            print(f"   • {service.name}")
            print(f"     Regular: ${service.price} → VIP: ${service.vip_price}")
            print(f"     Descuento: {discount_pct:.1f}% (${service.price - service.vip_price})")

    if services_without_vip.exists():
        issues.append(f"⚠️  {services_without_vip.count()} servicios activos sin precio VIP")

    # 3. Análisis de Punto de Equilibrio
    print("\n3. ANÁLISIS DE PUNTO DE EQUILIBRIO")
    print("-" * 70)

    if services_with_vip.exists():
        from django.db.models import Avg
        avg_price = services_with_vip.aggregate(avg=Avg('price'))['avg']
        avg_vip_price = services_with_vip.aggregate(avg=Avg('vip_price'))['avg']
        avg_savings = avg_price - avg_vip_price

        if avg_savings > 0:
            break_even_services = settings.vip_monthly_price / avg_savings

            print(f"   Precio promedio regular: ${avg_price:.2f}")
            print(f"   Precio promedio VIP: ${avg_vip_price:.2f}")
            print(f"   Ahorro promedio: ${avg_savings:.2f}")
            print(f"   Servicios para punto de equilibrio: {break_even_services:.2f}")
            print(f"   Servicios recomendados/mes: {int(break_even_services) + 1}")

            # ROI scenarios
            print("\n   ESCENARIOS DE ROI:")
            for num_services in [2, 3, 4, 5]:
                total_savings = avg_savings * num_services
                net_gain = total_savings - settings.vip_monthly_price
                print(f"   • {num_services} servicios/mes: Ahorro ${total_savings:.0f} - Membresía ${settings.vip_monthly_price} = ${net_gain:.0f}/mes")

    # 4. Verificar serializer
    print("\n4. VERIFICACIÓN DE API")
    print("-" * 70)

    from core.serializers import GlobalSettingsSerializer
    from django.test import RequestFactory
    from users.models import CustomUser

    # Crear request simulado con usuario VIP
    factory = RequestFactory()
    request = factory.get('/api/v1/settings/')

    # Simular usuario VIP
    try:
        vip_user = CustomUser.objects.filter(role='VIP').first()
        if not vip_user:
            # Crear usuario temporal para prueba
            vip_user = CustomUser(
                phone_number='+573000000000',
                role='VIP',
                is_verified=True
            )
    except:
        vip_user = None

    request.user = vip_user if vip_user else CustomUser()

    serializer = GlobalSettingsSerializer(settings, context={'request': request})
    data = serializer.data

    # Verificar campos clave
    expected_fields = ['vip_monthly_price', 'loyalty_months_required', 'loyalty_voucher_service_name']

    print(f"   Campos esperados en API:")
    for field in expected_fields:
        if field in data:
            print(f"   ✓ {field}: {data[field]}")
        else:
            print(f"   ✗ {field}: FALTANTE")
            issues.append(f"⚠️  Campo '{field}' no está en el serializer")

    # 5. Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)

    if issues:
        print("\n⚠️  PROBLEMAS ENCONTRADOS:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("\n✅ CONFIGURACIÓN VIP CORRECTA")
        print(f"\n   Precio VIP: ${settings.vip_monthly_price} COP/mes")
        print(f"   Servicios con precio VIP: {services_with_vip.count()}")
        print(f"   Punto de equilibrio: ~{int(break_even_services) + 1} servicios/mes")

    # 6. Endpoints disponibles
    print("\n" + "=" * 70)
    print("ENDPOINTS DISPONIBLES")
    print("=" * 70)
    print("\n   Configuración VIP:")
    print("   GET /api/v1/settings/")
    print("   Requiere: IsAuthenticated")
    print("   Retorna: vip_monthly_price, loyalty_months_required, etc.")

    print("\n   Iniciar Suscripción VIP:")
    print("   POST /api/v1/finances/payments/vip-subscription/initiate/")
    print("   Requiere: IsAuthenticated, IsVerified")
    print("   Retorna: Datos para widget de Wompi")

    print("\n   Cancelar Auto-Renovación:")
    print("   POST /api/v1/spa/vip/cancel-subscription/")
    print("   Requiere: IsAuthenticated, IsVerified")

    print("\n   Historial de Pagos:")
    print("   GET /api/v1/finances/payments/my/")
    print("   Requiere: IsAuthenticated")

    print("\n   Servicios (con precios VIP):")
    print("   GET /api/v1/services/")
    print("   Requiere: Ninguno (público)")
    print("   Nota: Cada servicio incluye 'price' y 'vip_price'")

    print("\n" + "=" * 70)

    return len(issues) == 0


if __name__ == '__main__':
    success = verify_vip_configuration()
    sys.exit(0 if success else 1)
