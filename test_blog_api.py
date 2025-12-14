"""
Script de prueba rápida para verificar que la API del blog funciona correctamente.
Ejecutar: python test_blog_api.py
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1/blog"

def test_endpoints():
    print("🧪 Probando endpoints del blog...\n")

    tests = [
        {
            "name": "Listar artículos",
            "url": f"{BASE_URL}/articles/",
            "expected_keys": ["count", "results"]
        },
        {
            "name": "Artículos destacados",
            "url": f"{BASE_URL}/articles/featured/",
            "expected_keys": None
        },
        {
            "name": "Artículos recientes",
            "url": f"{BASE_URL}/articles/recent/",
            "expected_keys": None
        },
        {
            "name": "Artículos populares",
            "url": f"{BASE_URL}/articles/popular/",
            "expected_keys": None
        },
        {
            "name": "Listar categorías",
            "url": f"{BASE_URL}/categories/",
            "expected_keys": ["count", "results"]
        },
        {
            "name": "Listar etiquetas",
            "url": f"{BASE_URL}/tags/",
            "expected_keys": ["count", "results"]
        },
    ]

    for test in tests:
        try:
            response = requests.get(test["url"], timeout=5)

            if response.status_code == 200:
                data = response.json()

                # Verificar estructura si se especificó
                if test["expected_keys"]:
                    missing = [k for k in test["expected_keys"] if k not in data]
                    if missing:
                        print(f"⚠️  {test['name']}: Faltan keys {missing}")
                    else:
                        count = data.get("count", len(data))
                        print(f"✅ {test['name']}: OK ({count} items)")
                else:
                    count = len(data)
                    print(f"✅ {test['name']}: OK ({count} items)")
            else:
                print(f"❌ {test['name']}: HTTP {response.status_code}")

        except requests.exceptions.ConnectionError:
            print(f"❌ {test['name']}: No se pudo conectar al servidor")
            print("   Asegúrate de que el servidor esté corriendo: python manage.py runserver")
            return
        except Exception as e:
            print(f"❌ {test['name']}: Error - {str(e)}")

    print("\n🎉 Pruebas completadas!")
    print("\n📋 Próximos pasos:")
    print("   1. Accede al admin: http://localhost:8000/admin/blog/")
    print("   2. Explora la API: http://localhost:8000/api/v1/blog/articles/")
    print("   3. Lee la docs: docs/BLOG_SYSTEM.md")

if __name__ == "__main__":
    test_endpoints()
