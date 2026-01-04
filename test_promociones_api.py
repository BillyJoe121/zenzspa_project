"""
Script para probar el API de promociones directamente.
Simula requests HTTP para identificar problemas.
"""
import os
import sys
import django

# Fix encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from django.test import RequestFactory
from rest_framework.test import force_authenticate
from promociones.views import PromocionViewSet
from promociones.models import Promocion
from django.contrib.auth import get_user_model
import json

User = get_user_model()

def create_admin_user():
    """Crea o obtiene un usuario admin para las pruebas"""
    user, created = User.objects.get_or_create(
        email='admin@test.com',
        defaults={
            'first_name': 'Admin',
            'last_name': 'Test',
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created:
        user.set_password('testpass123')
        user.save()
    return user


def test_api_retrieve_and_update():
    """Simula GET y PATCH a través del API"""
    print("\n" + "="*80)
    print("TEST: Retrieve (GET) y Update (PATCH) via API")
    print("="*80)

    factory = RequestFactory()
    admin_user = create_admin_user()

    # Crear promoción de prueba
    promo = Promocion.objects.create(
        titulo="Test API",
        descripcion="Descripción original con <b>HTML</b>",
        paginas=["dashboard", "home", "services"],
        tipo="popup",
        activa=True
    )
    print(f"\n1. Promoción creada:")
    print(f"   ID: {promo.id}")
    print(f"   Descripción: {promo.descripcion}")
    print(f"   Páginas: {promo.paginas}")

    # Simular GET (retrieve)
    print(f"\n2. Simulando GET /api/promociones/{promo.id}/")
    request = factory.get(f'/api/promociones/{promo.id}/')
    force_authenticate(request, user=admin_user)

    view = PromocionViewSet.as_view({'get': 'retrieve'})
    response = view(request, pk=promo.id)

    print(f"   Status: {response.status_code}")
    print(f"   Descripción en response: {response.data.get('descripcion')}")
    print(f"   Páginas en response: {response.data.get('paginas')}")

    # Simular PATCH (partial update) - solo cambiar título
    print(f"\n3. Simulando PATCH /api/promociones/{promo.id}/ (solo título)")
    patch_data = {
        'titulo': 'Título actualizado'
    }
    request = factory.patch(
        f'/api/promociones/{promo.id}/',
        data=json.dumps(patch_data),
        content_type='application/json'
    )
    force_authenticate(request, user=admin_user)

    view = PromocionViewSet.as_view({'patch': 'partial_update'})
    response = view(request, pk=promo.id)

    print(f"   Status: {response.status_code}")
    print(f"   Descripción en response: {response.data.get('descripcion')}")
    print(f"   Páginas en response: {response.data.get('paginas')}")

    # Verificar en DB
    promo.refresh_from_db()
    print(f"\n4. Verificación en DB después de PATCH:")
    print(f"   Descripción: {promo.descripcion}")
    print(f"   Páginas: {promo.paginas}")
    print(f"   ¿Descripción persiste? {'SÍ' if promo.descripcion == 'Descripción original con <b>HTML</b>' else 'NO'}")
    print(f"   ¿Páginas persisten? {'SÍ' if promo.paginas == ['dashboard', 'home', 'services'] else 'NO'}")

    # Limpiar
    promo.delete()
    print(f"\n✓ Promoción eliminada")


def test_api_update_with_multipart():
    """Simula PUT/PATCH con multipart/form-data (como cuando se sube imagen)"""
    print("\n" + "="*80)
    print("TEST: Update con multipart/form-data")
    print("="*80)

    factory = RequestFactory()
    admin_user = create_admin_user()

    # Crear promoción
    promo = Promocion.objects.create(
        titulo="Test Multipart",
        descripcion="Descripción original multipart",
        paginas=["dashboard", "home"],
        tipo="popup",
        activa=True
    )
    print(f"\n1. Promoción creada:")
    print(f"   ID: {promo.id}")
    print(f"   Descripción: {promo.descripcion}")
    print(f"   Páginas: {promo.paginas}")

    # Simular PATCH con form-data (como desde frontend con FormData)
    print(f"\n2. Simulando PATCH con multipart/form-data")

    # Datos como los envía FormData (todos strings)
    form_data = {
        'titulo': 'Título desde FormData',
        'descripcion': 'Nueva descripción desde FormData',
        'tipo': 'popup',
        'paginas': '["dashboard","services"]',  # JSON string
        'activa': 'true'
    }

    request = factory.patch(
        f'/api/promociones/{promo.id}/',
        data=form_data
    )
    force_authenticate(request, user=admin_user)

    view = PromocionViewSet.as_view({'patch': 'partial_update'})
    response = view(request, pk=promo.id)

    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   Descripción en response: {response.data.get('descripcion')}")
        print(f"   Páginas en response: {response.data.get('paginas')}")
    else:
        print(f"   Errores: {response.data}")

    # Verificar en DB
    promo.refresh_from_db()
    print(f"\n3. Verificación en DB:")
    print(f"   Descripción: {promo.descripcion}")
    print(f"   Páginas: {promo.paginas}")

    # Limpiar
    promo.delete()
    print(f"\n✓ Promoción eliminada")


def test_api_update_empty_fields():
    """Prueba enviar campos vacíos"""
    print("\n" + "="*80)
    print("TEST: Update con campos vacíos o faltantes")
    print("="*80)

    factory = RequestFactory()
    admin_user = create_admin_user()

    # Crear promoción
    promo = Promocion.objects.create(
        titulo="Test Campos Vacíos",
        descripcion="Descripción que no debe borrarse",
        paginas=["dashboard", "home"],
        tipo="popup",
        activa=True
    )
    print(f"\n1. Promoción creada:")
    print(f"   Descripción: {promo.descripcion}")
    print(f"   Páginas: {promo.paginas}")

    # Simular PATCH sin descripción ni páginas
    print(f"\n2. Simulando PATCH sin descripción ni páginas")
    patch_data = {
        'activa': False
    }

    request = factory.patch(
        f'/api/promociones/{promo.id}/',
        data=json.dumps(patch_data),
        content_type='application/json'
    )
    force_authenticate(request, user=admin_user)

    view = PromocionViewSet.as_view({'patch': 'partial_update'})
    response = view(request, pk=promo.id)

    print(f"   Status: {response.status_code}")

    # Verificar
    promo.refresh_from_db()
    print(f"\n3. Verificación después de PATCH (solo activa):")
    print(f"   Activa: {promo.activa}")
    print(f"   Descripción: {promo.descripcion}")
    print(f"   Páginas: {promo.paginas}")
    print(f"   ¿Descripción persiste? {'SÍ' if promo.descripcion == 'Descripción que no debe borrarse' else 'NO'}")
    print(f"   ¿Páginas persisten? {'SÍ' if promo.paginas == ['dashboard', 'home'] else 'NO'}")

    # Probar con campos explícitamente vacíos
    print(f"\n4. Simulando PATCH con descripción='' y paginas=[]")
    patch_data = {
        'descripcion': '',
        'paginas': []
    }

    request = factory.patch(
        f'/api/promociones/{promo.id}/',
        data=json.dumps(patch_data),
        content_type='application/json'
    )
    force_authenticate(request, user=admin_user)

    view = PromocionViewSet.as_view({'patch': 'partial_update'})
    response = view(request, pk=promo.id)

    print(f"   Status: {response.status_code}")

    # Verificar
    promo.refresh_from_db()
    print(f"\n5. Verificación después de PATCH con valores vacíos:")
    print(f"   Descripción: '{promo.descripcion}'")
    print(f"   Páginas: {promo.paginas}")
    print(f"   ¿Descripción se vació? {'SÍ' if promo.descripcion == '' else 'NO'}")
    print(f"   ¿Páginas se vaciaron? {'SÍ' if promo.paginas == [] else 'NO'}")

    # Limpiar
    promo.delete()
    print(f"\n✓ Promoción eliminada")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("PRUEBAS DE API DE PROMOCIONES")
    print("="*80)

    try:
        test_api_retrieve_and_update()
        test_api_update_with_multipart()
        test_api_update_empty_fields()

        print("\n" + "="*80)
        print("TODAS LAS PRUEBAS COMPLETADAS")
        print("="*80)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
