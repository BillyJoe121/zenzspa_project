from django.db import transaction
from .models import Order, OrderItem, Product

class OrderCreationService:
    """
    Servicio para encapsular la lógica de creación de una orden a partir de un carrito.
    """
    def __init__(self, user, cart, data):
        self.user = user
        self.cart = cart
        self.data = data # Datos del request (ej. delivery_option)

    @transaction.atomic
    def create_order(self):
        """
        Crea una orden de forma atómica. Esto asegura que si algo falla,
        toda la operación se revierte.
        """
        # 1. Validar que el carrito no esté vacío
        if not self.cart.items.exists():
            raise ValueError("No se puede crear una orden con un carrito vacío.")

        # 2. Crear la orden inicial
        order = Order.objects.create(
            user=self.user,
            delivery_option=self.data.get('delivery_option'),
            delivery_address=self.data.get('delivery_address'),
            associated_appointment=self.data.get('associated_appointment'),
            total_amount=0 # Se calculará a continuación
        )

        total_amount = 0
        items_to_create = []

        # 3. Iterar sobre los ítems del carrito para crear los ítems de la orden
        for cart_item in self.cart.items.all():
            product = cart_item.product
            
            # Bloquear el producto para evitar race conditions en el stock
            Product.objects.select_for_update().get(id=product.id)

            # Validar stock una última vez
            if product.stock < cart_item.quantity:
                raise ValueError(f"Stock insuficiente para el producto '{product.name}'.")

            # Decidir qué precio usar (VIP o regular)
            price_at_purchase = product.price
            if self.user.is_vip and product.vip_price:
                price_at_purchase = product.vip_price
            
            total_amount += price_at_purchase * cart_item.quantity
            
            items_to_create.append(
                OrderItem(
                    order=order,
                    product=product,
                    quantity=cart_item.quantity,
                    price_at_purchase=price_at_purchase
                )
            )
            
            # Actualizar el stock del producto
            product.stock -= cart_item.quantity
            product.save()

        # 4. Crear todos los OrderItem en una sola consulta y actualizar el total
        OrderItem.objects.bulk_create(items_to_create)
        order.total_amount = total_amount
        order.save()

        # 5. Vaciar el carrito de compras
        self.cart.items.all().delete()
        
        return order