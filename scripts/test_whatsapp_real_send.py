
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
    target_phone = "+573157589548"
    
    # Template: APPOINTMENT_REMINDER_2H
    # Content SID: HX7c977d8ead9bac2813a66b58754cc917
    # Variables: ["user_name", "start_time", "services"]
    
    content_sid = "HX7c977d8ead9bac2813a66b58754cc917"
    
    # Try sending with named keys first, as implied by the template definition file
    variables = {
        "user_name": "Usuario Test",
        "start_time": "14:00",
        "services": "Consulta General"
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
