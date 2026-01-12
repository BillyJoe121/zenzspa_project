import os
import sys
import django

sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiozens.settings")
django.setup()

from spa.models import Service

def check_low_supervision():
    print("--- Low Supervision Services ---")
    services = Service.objects.filter(category__is_low_supervision=True, is_active=True)
    
    if not services.exists():
        print("No active low supervision services found.")
        return

    for s in services:
        print(f"- {s.name} (Category: {s.category.name})")

if __name__ == "__main__":
    check_low_supervision()
