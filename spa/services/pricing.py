from decimal import Decimal
from django.db import transaction
from spa.models import Service

def update_service_vip_prices(discount_percentage=None):
    """
    Actualiza los precios VIP de todos los servicios activos basado en un porcentaje de descuento.
    
    Args:
        discount_percentage (Decimal, optional): Porcentaje a aplicar (e.g. 15.00).
                                               Si es None, se lee de GlobalSettings.
    Returns:
        int: Número de servicios actualizados.
    """
    # Importar aquí para evitar importaciones circulares en el arranque
    from core.models.settings import GlobalSettings
    
    if discount_percentage is None:
        settings = GlobalSettings.load()
        # Fallback a 15 si el campo no existe aún (durante migraciones/deploy)
        discount_percentage = getattr(settings, 'vip_discount_percentage', Decimal('15.00'))
    
    # Asegurarnos de trabajar con Decimal
    if not isinstance(discount_percentage, Decimal):
        discount_percentage = Decimal(str(discount_percentage))
        
    # Convertir porcentaje a factor (e.g. 15 -> 0.15)
    discount_factor = discount_percentage / Decimal('100.00')
    
    services = Service.objects.filter(is_active=True)
    updated_count = 0
    
    with transaction.atomic():
        for service in services:
            if not service.price:
                continue
                
            # Calcular precio VIP
            vip_price = service.price * (Decimal('1') - discount_factor)
            vip_price = vip_price.quantize(Decimal('0.01'))  # Redondear a 2 decimales
            
            # Actualizar solo si cambió
            if service.vip_price != vip_price:
                service.vip_price = vip_price
                service.save(update_fields=['vip_price'])
                updated_count += 1
                
    return updated_count
