
import os
import sys
import django

# Add project root to sys.path
sys.path.append('/app')

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from notifications.whatsapp_service import WhatsAppService

def send_test_message():
    target_phone = "+573163237572"
    
    # Template: APPOINTMENT_REMINDER_24H
    # Content SID: HX312e18d0e6d472368178c3755e3f4bb3
    
    content_sid = "HX312e18d0e6d472368178c3755e3f4bb3"
    
    variables = {
        "user_name": "Maria Velez",
        "start_date": "07 Enero 2025",
        "start_time": "4:00 PM",
        "services": "Masaje Relajante",
        "total": "$150.000 COP"
    }

    print(f"Sending WhatsApp to {target_phone} using SID {content_sid}...")
    print(f"Variables: {variables}")

    result = WhatsAppService.send_template_message(
        to_phone=target_phone,
        content_sid=content_sid,
        content_variables=variables
    )

    if result.get("success"):
        print(f"✅ Message sent successfully! SID: {result.get('sid')}")
    else:
        print(f"❌ Failed to send message: {result.get('error')}")

if __name__ == "__main__":
    send_test_message()
