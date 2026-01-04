"""
Script de prueba para verificar el comportamiento de promociones en el backend.
Simula operaciones CRUD para identificar problemas con descripcion y paginas.
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

from promociones.models import Promocion
from promociones.serializers import PromocionSerializer

def test_descripcion_persistence():
    """Prueba 1: Verificar persistencia de descripción"""
    print("\n" + "="*80)
    print("PRUEBA 1: Persistencia de descripción")
    print("="*80)

    # Crear promoción de prueba
    promo = Promocion.objects.create(
        titulo="Test Descripción",
        descripcion="Esta es una descripción de prueba con <b>HTML</b>",
        paginas=["dashboard", "home"],
        tipo="popup"
    )
    print(f"✓ Promoción creada con ID: {promo.id}")
    print(f"  - Descripción original: {promo.descripcion}")

    # Simular lectura (como en GET)
    promo_leida = Promocion.objects.get(id=promo.id)
    print(f"\n✓ Promoción leída desde DB:")
    print(f"  - Descripción: {promo_leida.descripcion}")

    # Simular serialización (como en GET API)
    serializer = PromocionSerializer(promo_leida)
    print(f"\n✓ Datos serializados (GET):")
    print(f"  - Descripción: {serializer.data.get('descripcion')}")

    # Simular actualización (como en PUT/PATCH)
    update_data = {
        'titulo': 'Test Descripción Actualizado',
        'descripcion': 'Nueva descripción con <i>italic</i>',
        'tipo': 'popup',
        'paginas': ['dashboard'],
        'activa': True
    }

    serializer = PromocionSerializer(promo_leida, data=update_data, partial=False)
    if serializer.is_valid():
        serializer.save()
        print(f"\n✓ Promoción actualizada")
        print(f"  - Nueva descripción: {serializer.instance.descripcion}")
    else:
        print(f"\n✗ Error al actualizar: {serializer.errors}")

    # Verificar que persiste
    promo_final = Promocion.objects.get(id=promo.id)
    print(f"\n✓ Verificación final:")
    print(f"  - Descripción en DB: {promo_final.descripcion}")
    print(f"  - ¿Descripción persiste? {'SÍ' if promo_final.descripcion == update_data['descripcion'] else 'NO'}")

    # Limpiar
    promo.delete()
    print(f"\n✓ Promoción de prueba eliminada")


def test_paginas_persistence():
    """Prueba 2: Verificar persistencia de páginas"""
    print("\n" + "="*80)
    print("PRUEBA 2: Persistencia de páginas")
    print("="*80)

    # Crear promoción de prueba
    promo = Promocion.objects.create(
        titulo="Test Páginas",
        descripcion="Descripción de prueba",
        paginas=["dashboard", "home", "services"],
        tipo="banner"
    )
    print(f"✓ Promoción creada con ID: {promo.id}")
    print(f"  - Páginas originales: {promo.paginas}")

    # Simular lectura
    promo_leida = Promocion.objects.get(id=promo.id)
    print(f"\n✓ Promoción leída desde DB:")
    print(f"  - Páginas: {promo_leida.paginas}")

    # Simular serialización
    serializer = PromocionSerializer(promo_leida)
    print(f"\n✓ Datos serializados (GET):")
    print(f"  - Páginas: {serializer.data.get('paginas')}")

    # Simular actualización PATCH (solo cambiar título, NO páginas)
    update_data = {
        'titulo': 'Test Páginas Actualizado',
    }

    serializer = PromocionSerializer(promo_leida, data=update_data, partial=True)
    if serializer.is_valid():
        serializer.save()
        print(f"\n✓ Promoción actualizada (PATCH - solo título)")
        print(f"  - Título nuevo: {serializer.instance.titulo}")
        print(f"  - Páginas después de PATCH: {serializer.instance.paginas}")
    else:
        print(f"\n✗ Error al actualizar: {serializer.errors}")

    # Verificar que páginas persisten
    promo_final = Promocion.objects.get(id=promo.id)
    print(f"\n✓ Verificación final:")
    print(f"  - Páginas en DB: {promo_final.paginas}")
    print(f"  - ¿Páginas persisten? {'SÍ' if promo_final.paginas == ['dashboard', 'home', 'services'] else 'NO'}")

    # Probar actualización completa PUT con páginas nuevas
    update_data_put = {
        'titulo': 'Test PUT',
        'descripcion': 'Descripción PUT',
        'tipo': 'banner',
        'paginas': ['shop'],
        'activa': True
    }

    serializer = PromocionSerializer(promo_final, data=update_data_put, partial=False)
    if serializer.is_valid():
        serializer.save()
        print(f"\n✓ Promoción actualizada (PUT - con páginas)")
        print(f"  - Páginas nuevas: {serializer.instance.paginas}")
    else:
        print(f"\n✗ Error al actualizar con PUT: {serializer.errors}")

    promo_final_2 = Promocion.objects.get(id=promo.id)
    print(f"\n✓ Verificación final después de PUT:")
    print(f"  - Páginas en DB: {promo_final_2.paginas}")
    print(f"  - ¿Páginas actualizadas correctamente? {'SÍ' if promo_final_2.paginas == ['shop'] else 'NO'}")

    # Limpiar
    promo.delete()
    print(f"\n✓ Promoción de prueba eliminada")


def test_formdata_processing():
    """Prueba 3: Simular envío de FormData desde frontend"""
    print("\n" + "="*80)
    print("PRUEBA 3: Procesamiento de FormData")
    print("="*80)

    # Simular datos como vienen desde FormData (todos strings)
    formdata_like = {
        'titulo': 'Test FormData',
        'descripcion': 'Descripción desde FormData',
        'tipo': 'popup',
        'paginas': '["dashboard","home"]',  # JSON string
        'activa': 'true',  # String boolean
        'mostrar_siempre': 'false'  # String boolean
    }

    print(f"✓ Datos recibidos (simulando FormData):")
    for key, value in formdata_like.items():
        print(f"  - {key}: {value} (tipo: {type(value).__name__})")

    # Procesar con serializer
    serializer = PromocionSerializer(data=formdata_like)

    print(f"\n✓ Validación del serializer:")
    if serializer.is_valid():
        print(f"  - ✓ Datos válidos")
        promo = serializer.save()
        print(f"\n✓ Promoción creada con ID: {promo.id}")
        print(f"  - Descripción guardada: {promo.descripcion}")
        print(f"  - Páginas guardadas: {promo.paginas}")
        print(f"  - Activa: {promo.activa} (tipo: {type(promo.activa).__name__})")

        # Leer de nuevo
        promo_leida = Promocion.objects.get(id=promo.id)
        serializer_read = PromocionSerializer(promo_leida)

        print(f"\n✓ Lectura después de guardar:")
        print(f"  - Descripción: {serializer_read.data.get('descripcion')}")
        print(f"  - Páginas: {serializer_read.data.get('paginas')}")

        # Limpiar
        promo.delete()
        print(f"\n✓ Promoción de prueba eliminada")
    else:
        print(f"  - ✗ Errores de validación:")
        for field, errors in serializer.errors.items():
            print(f"    - {field}: {errors}")


def test_toggle_activa():
    """Prueba 4: Toggle de campo activa (como el botón externo)"""
    print("\n" + "="*80)
    print("PRUEBA 4: Toggle de campo 'activa' (botón externo)")
    print("="*80)

    # Crear promoción
    promo = Promocion.objects.create(
        titulo="Test Toggle",
        descripcion="Descripción para toggle",
        paginas=["dashboard", "home"],
        tipo="popup",
        activa=True
    )
    print(f"✓ Promoción creada con ID: {promo.id}")
    print(f"  - Estado inicial: activa={promo.activa}")
    print(f"  - Páginas iniciales: {promo.paginas}")
    print(f"  - Descripción inicial: {promo.descripcion}")

    # Simular toggle (PATCH solo del campo activa)
    toggle_data = {
        'activa': False
    }

    serializer = PromocionSerializer(promo, data=toggle_data, partial=True)
    if serializer.is_valid():
        serializer.save()
        print(f"\n✓ Toggle realizado (activa=False)")
    else:
        print(f"\n✗ Error en toggle: {serializer.errors}")

    # Verificar que páginas y descripción persisten
    promo_after_toggle = Promocion.objects.get(id=promo.id)
    print(f"\n✓ Verificación después de toggle:")
    print(f"  - Estado: activa={promo_after_toggle.activa}")
    print(f"  - Páginas: {promo_after_toggle.paginas}")
    print(f"  - Descripción: {promo_after_toggle.descripcion}")
    print(f"  - ¿Páginas persisten? {'SÍ' if promo_after_toggle.paginas == ['dashboard', 'home'] else 'NO'}")
    print(f"  - ¿Descripción persiste? {'SÍ' if promo_after_toggle.descripcion == 'Descripción para toggle' else 'NO'}")

    # Limpiar
    promo.delete()
    print(f"\n✓ Promoción de prueba eliminada")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DIAGNÓSTICO DE PROBLEMAS EN PROMOCIONES - BACKEND")
    print("="*80)

    try:
        test_descripcion_persistence()
        test_paginas_persistence()
        test_formdata_processing()
        test_toggle_activa()

        print("\n" + "="*80)
        print("TODAS LAS PRUEBAS COMPLETADAS")
        print("="*80)

    except Exception as e:
        print(f"\n✗ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
