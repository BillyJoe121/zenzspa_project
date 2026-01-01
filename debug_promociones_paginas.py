import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiozens.settings")
django.setup()

from promociones.models import Promocion

print("--- Inspección de Paginas en Promociones ---")
for p in Promocion.objects.all():
    tipo_dato = type(p.paginas)
    contenido = p.paginas
    print(f"ID: {p.id} | Tipo: {tipo_dato} | Contenido: {contenido}")
    
    # Detección de problema de doble encoding
    if isinstance(contenido, str):
        print(f"⚠️  ADVERTENCIA: El ID {p.id} tiene 'paginas' como string. Debería ser lista.")
        try:
            parsed = json.loads(contenido.replace("'", '"')) # Intento simple de fix
            if isinstance(parsed, list):
                print(f"   -> Se puede corregir a: {parsed}")
                p.paginas = parsed
                p.save()
                print("   -> ¡CORREGIDO AUTOMÁTICAMENTE!")
        except Exception as e:
            print(f"   -> No se pudo corregir automáticamente: {e}")
            
print("--- Fin ---")
