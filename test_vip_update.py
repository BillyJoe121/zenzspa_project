import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiozens.settings")
django.setup()

from core.models import GlobalSettings
from core.serializers import GlobalSettingsUpdateSerializer
from rest_framework.exceptions import ValidationError

def test_update_vip_price():
    print("--- Probando actualización de Precio VIP ---")
    
    settings = GlobalSettings.load()
    print(f"Precio actual: {settings.vip_monthly_price}")
    
    # Simular datos del frontend (request.data normalmente son strings/floats/ints)
    data = {
        "vip_monthly_price": "50000.00"
    }
    
    serializer = GlobalSettingsUpdateSerializer(
        settings,
        data=data,
        partial=True
    )
    
    try:
        serializer.is_valid(raise_exception=True)
        serializer.save()
        print("Update exitoso.")
        settings.refresh_from_db()
        print(f"Nuevo precio: {settings.vip_monthly_price}")
        
    except ValidationError as e:
        print(f"Error de validación: {e.detail}")
    except Exception as e:
        print(f"Error inesperado: {e}")

if __name__ == "__main__":
    test_update_vip_price()
