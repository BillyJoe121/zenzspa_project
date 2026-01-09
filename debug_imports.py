
import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

try:
    print("Importing PaymentService...")
    from finances.payments import PaymentService
    print("PaymentService imported successfully.")
    
    print("Importing apply_gateway_status dependencies...")
    from finances.payments.appointment_payments import calculate_outstanding_amount
    print("calculate_outstanding_amount imported successfully.")

    print("ALL IMPORTS OK")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
