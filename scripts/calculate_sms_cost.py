
import os
import django
from django.conf import settings

# Setup Django environment manually specifically for this script
import sys
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiozens.settings")
django.setup()

from notifications.models import NotificationTemplate
import math

COST_PER_SEGMENT_USD = 0.06  # Costo aproximado Twilio Colombia

def clean_text_for_gsm(text):
    """
    Simula la limpieza: quita emojis y formato markdown (*, _)
    para estimar caracteres en GSM-7 puro.
    """
    # 1. Quitar markdown simple
    clean = text.replace("*", "").replace("_", "")
    
    # 2. Quitar emojis (simplificado: quitar caracteres no ascii o non-latin basic)
    # En un caso real usaríamos librerías de unicode, aquí aproximamos
    # quitando caracteres fuera del rango básico imprimible extendido
    gsm_compatible = ""
    for char in clean:
        if ord(char) < 128: # Basic ASCII
            gsm_compatible += char
        # Se podrían mapear tildes a sin tilde para ahorrar, 
        # pero asumamos que se limpian o se cobran como GSM extendido (ocupa poco más)
        # Para el cálculo conservador, contamos caracteres.
            
    # Reducir espacios múltiples
    return " ".join(gsm_compatible.split())

def calculate_segments(text):
    # Longitud del mensaje con variables simuladas
    # Reemplazamos variables {{...}} con valores promedio
    simulated_text = text.replace("{{ user_name }}", "Maria Alejandra") \
                         .replace("{{ start_date }}", "25/12/2025") \
                         .replace("{{ start_time }}", "10:30 AM") \
                         .replace("{{ services }}", "Masaje Relajante y Spa") \
                         .replace("{{ total }}", "150.000") \
                         .replace("{{ amount }}", "150.000") \
                         .replace("{{ reference }}", "REF12345678") \
                         .replace("{{ voucher_code }}", "DESC-2024")
                         
    cleaned_text = clean_text_for_gsm(simulated_text)
    length = len(cleaned_text)
    
    # GSM-7 Limits:
    # 1 segmento: 160 chars
    # >1 segmento: 153 chars por segmento (debido al header de concatenación)
    
    if length <= 160:
        segments = 1
    else:
        segments = math.ceil(length / 153.0)
        
    return {
        "original_len": len(text),
        "simulated_len": length,
        "segments": segments,
        "cost": segments * COST_PER_SEGMENT_USD,
        "preview": cleaned_text[:50] + "..."
    }

print(f"{'EVENTO':<35} | {'SARS' :<5} | {'LEN':<4} | {'$$ USD':<8}")
print("-" * 60)

total_estimated_cost = 0
templates = NotificationTemplate.objects.filter(channel="WHATSAPP")

count = 0
for t in templates:
    data = calculate_segments(t.body_template)
    print(f"{t.event_code[:35]:<35} | {data['segments']:<5} | {data['simulated_len']:<4} | ${data['cost']:.2f}")
    total_estimated_cost += data['cost']
    count += 1

if count > 0:
    avg_cost = total_estimated_cost / count
    print("-" * 60)
    print(f"PROMEDIO POR NOTIFICACIÓN: ${avg_cost:.2f} USD")
    print(f"PROMEDIO EN COP (@ 4100): ${avg_cost * 4100:.0f} COP")
else:
    print("No se encontraron templates.")
