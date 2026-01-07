"""
Script de prueba para verificar la búsqueda de créditos.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from finances.models import ClientCredit
from users.models import CustomUser

print("=" * 60)
print("PRUEBA DE BÚSQUEDA DE CRÉDITOS")
print("=" * 60)

# Obtener algunos usuarios con créditos
credits_sample = ClientCredit.objects.select_related('user').all()[:5]

if credits_sample.exists():
    print(f"\n[OK] Se encontraron {ClientCredit.objects.count()} creditos en total\n")
    print("Ejemplo de datos disponibles para busqueda:\n")

    for credit in credits_sample:
        user = credit.user
        print(f"[*] Credito ID: {credit.id}")
        print(f"   Usuario: {user.first_name} {user.last_name}")
        print(f"   Telefono: {user.phone_number}")
        print(f"   Email: {user.email or 'N/A'}")
        print(f"   Saldo: ${credit.remaining_amount} de ${credit.initial_amount}")
        print(f"   Estado: {credit.status}")
        print()

    print("\n" + "=" * 60)
    print("ENDPOINTS DISPONIBLES PARA EL FRONTEND:")
    print("=" * 60)
    print()
    print("[BUSQUEDA POR NOMBRE]")
    if credits_sample.first().user.first_name:
        ejemplo_nombre = credits_sample.first().user.first_name[:3]
        print(f"   GET /api/v1/finances/admin/credits/?search={ejemplo_nombre}")

    print("\n[BUSQUEDA POR TELEFONO]")
    if credits_sample.first().user.phone_number:
        ejemplo_tel = credits_sample.first().user.phone_number[-4:]
        print(f"   GET /api/v1/finances/admin/credits/?search={ejemplo_tel}")

    print("\n[BUSQUEDA POR EMAIL]")
    if credits_sample.first().user.email:
        print(f"   GET /api/v1/finances/admin/credits/?search={credits_sample.first().user.email}")

    print("\n[FILTRAR POR ESTADO]")
    print("   GET /api/v1/finances/admin/credits/?status=AVAILABLE")
    print("   GET /api/v1/finances/admin/credits/?status=PARTIALLY_USED")
    print("   GET /api/v1/finances/admin/credits/?status=USED")
    print("   GET /api/v1/finances/admin/credits/?status=EXPIRED")

    print("\n[FILTRAR POR USUARIO]")
    if credits_sample.first().user:
        print(f"   GET /api/v1/finances/admin/credits/?user={credits_sample.first().user.id}")

    print("\n[COMBINAR BUSQUEDA + FILTRO]")
    if credits_sample.first().user.first_name:
        ejemplo_nombre = credits_sample.first().user.first_name[:3]
        print(f"   GET /api/v1/finances/admin/credits/?search={ejemplo_nombre}&status=AVAILABLE")

    print("\n[ORDENAR RESULTADOS]")
    print("   GET /api/v1/finances/admin/credits/?ordering=-created_at")
    print("   GET /api/v1/finances/admin/credits/?ordering=expires_at")
    print("   GET /api/v1/finances/admin/credits/?ordering=-remaining_amount")

else:
    print("\n[!] No hay creditos en la base de datos para mostrar ejemplos.")
    print("   Primero crea algunos creditos para probar la busqueda.")

print("\n" + "=" * 60)
