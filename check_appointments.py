from spa.models import Appointment
from finances.models import Payment
from decimal import Decimal

print('=' * 100)
print(f'{"CLIENTE":<12} {"ROL":<8} {"FECHA":<12} {"ESTADO":<12} {"TOTAL":>12} {"ANTICIPO":>12} {"PAGADO":>12} {"TIPO PAGO":<15}')
print('=' * 100)

for appt in Appointment.objects.prefetch_related('payments').select_related('user').order_by('start_time'):
    payments = list(appt.payments.filter(status='APPROVED'))
    total_paid = sum(p.amount for p in payments)
    
    advance = [p for p in payments if p.payment_type == 'ADVANCE']
    final = [p for p in payments if p.payment_type == 'FINAL']
    
    advance_amount = advance[0].amount if advance else Decimal('0')
    
    if final and not advance:
        tipo = 'PAGO COMPLETO'
    elif advance and not final:
        tipo = 'SOLO ANTICIPO'
    else:
        tipo = 'ANT + FINAL'
    
    print(f'{appt.user.first_name:<12} {appt.user.role:<8} {appt.start_time.strftime("%Y-%m-%d"):<12} {appt.status:<12} ${appt.price_at_purchase:>10,.0f} ${advance_amount:>10,.0f} ${total_paid:>10,.0f} {tipo:<15}')

print('=' * 100)
print()

# Verificar un servicio VIP
from users.models import CustomUser
vip_user = CustomUser.objects.filter(role='VIP').first()
if vip_user:
    print(f'Usuario VIP: {vip_user.first_name}')
    vip_appts = Appointment.objects.filter(user=vip_user)
    for a in vip_appts:
        items = a.items.select_related('service').all()
        print(f'  Cita {a.start_time.strftime("%Y-%m-%d")}: Total ${a.price_at_purchase:,.0f}')
        for item in items:
            print(f'    - {item.service.name}: ${item.price_at_purchase:,.0f} (normal: ${item.service.price:,.0f}, VIP: ${item.service.vip_price:,.0f})')
