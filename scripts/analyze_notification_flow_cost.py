
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiozens.settings")
django.setup()

from notifications.models import NotificationTemplate
import math

COST_PER_SEGMENT = 0.06

# Eventos mapeados según flujo de negocio
FLOWS = {
    "MINIMO": [
        "ADMIN_APPOINTMENT_CASH_PENDING", # Confirmación inicial (si es efectivo) o PAYMENT_APPROVED
        "APPOINTMENT_REMINDER_24H",     # Recordatorio día antes
        # Asume que llega, no cancela, no compra nada extra
    ],
    "ESTANDAR": [
        "PAYMENT_STATUS_APPROVED",      # Pago reserva
        "APPOINTMENT_REMINDER_24H",     # Recordatorio 24h
        "APPOINTMENT_REMINDER_2H",      # Recordatorio 2h
        # Cliente asiste, todo normal
    ],
    "EXTENSO": [
        "PAYMENT_STATUS_APPROVED",      # Reserva inicial
        "APPOINTMENT_REMINDER_24H",     # Recordatorio original
        "APPOINTMENT_CANCELLED_AUTO",   # Digamos que reprograma o cancela
        "APPOINTMENT_WAITLIST_AVAILABLE", # Se le avisa de nuevo espacio
        "PAYMENT_STATUS_APPROVED",      # Paga/Reserva de nuevo
        "APPOINTMENT_REMINDER_24H",     # Nuevo recordatorio
        "APPOINTMENT_REMINDER_2H",      # Recordatorio 2h
        "ORDER_CREDIT_ISSUED",          # Quizás una devolución parcial o ajuste
        "VIP_LOYALTY_MILESTONE",        # Se vuelve VIP tras la cita
    ]
}

def clean_text_for_gsm(text):
    clean = text.replace("*", "").replace("_", "")
    gsm_compatible = ""
    for char in clean:
        if ord(char) < 128:
            gsm_compatible += char
    return " ".join(gsm_compatible.split())

def get_cost_for_event(event_code):
    try:
        template = NotificationTemplate.objects.get(event_code=event_code, channel="WHATSAPP")
        # Simulación de variables
        simulated_text = template.body_template.replace("{{ user_name }}", "Maria Alejandra") \
                             .replace("{{ start_date }}", "25/12/2025") \
                             .replace("{{ start_time }}", "10:30 AM") \
                             .replace("{{ services }}", "Masaje Relajante y Spa") \
                             .replace("{{ total }}", "150.000")
        
        cleaned = clean_text_for_gsm(simulated_text)
        length = len(cleaned)
        segments = 1 if length <= 160 else math.ceil(length / 153.0)
        return segments * COST_PER_SEGMENT
    except NotificationTemplate.DoesNotExist:
        return 0.12 # Promedio default si no existe template aun (ej. los nuevos de admin)

print(f"{'ESCENARIO':<15} | {'CANT':<5} | {'COSTO TOTAL (USD)':<18} | {'COSTO (COP)':<15}")
print("-" * 65)

for scenario, events in FLOWS.items():
    total_cost = 0
    count = 0
    for event in events:
        cost = get_cost_for_event(event)
        total_cost += cost
        count += 1
    
    cop_cost = total_cost * 4100
    print(f"{scenario:<15} | {count:<5} | ${total_cost:<17.2f} | ${cop_cost:<14,.0f}")

print("\nDETALLE DE COSTOS POR EVENTO (ESTIMADO):")
unique_events = set(sum(FLOWS.values(), []))
for event in unique_events:
    cost = get_cost_for_event(event)
    print(f"- {event}: ${cost:.2f}")
