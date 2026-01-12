import logging
from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from finances.payments import PaymentService
from users.models import CustomUser
from users.permissions import IsAdminUser as DomainIsAdminUser

from ..models import InventoryMovement, Order
from ..serializers import (
    OrderSerializer,
    ReturnDecisionSerializer,
    ReturnRequestSerializer,
)
from ..services import ReturnService

logger = logging.getLogger(__name__)


class OrderActionsMixin:
    @action(detail=True, methods=['post'], url_path='retry-payment')
    @transaction.atomic
    def retry_payment(self, request, pk=None):
        """
        Permite reintentar el pago de una orden existente que esté pendiente.
        Genera una nueva referencia de Wompi para evitar errores de "referencia duplicada".

        Body (opcional):
            use_credits: bool - Si debe usar créditos disponibles del usuario
        """
        try:
            order = self.get_object() # Valida permission classes y queryset filter
        except Exception:
            return Response({"error": "Orden no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if order.status != Order.OrderStatus.PENDING_PAYMENT:
             return Response(
                {"error": f"No se puede pagar una orden en estado {order.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extraer el parámetro use_credits del request
        use_credits = request.data.get('use_credits', False)

        # Regenerar pago y referencia usando el servicio
        try:
            payment, payment_payload = PaymentService.create_order_payment(
                request.user,
                order,
                use_credits=use_credits
            )
        except ValueError as e:
            logger.error("Error al reintentar pago de orden %s: %s", order.id, e)
            return Response(
                {"error": str(e), "code": "MKT-PAYMENT-RETRY-ERROR"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # Retornar estructura similar al checkout para reutilizar lógica frontend
        order_serializer = self.get_serializer(order)
        response_data = {
            'order': order_serializer.data,
            'payment': payment_payload,
        }
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='request-return')
    def request_return(self, request, pk=None):
        order = self.get_object()
        if order.user != request.user:
            return Response(
                {"detail": "Solo el dueño de la orden puede solicitar devoluciones."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ReturnRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated_order = ReturnService.request_return(
                order,
                serializer.validated_data['items'],
                serializer.validated_data['reason'],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(updated_order).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='process-return',
        permission_classes=[DomainIsAdminUser],
    )
    def process_return(self, request, pk=None):
        order = self.get_object()
        serializer = ReturnDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated_order = ReturnService.process_return(
                order,
                approved=serializer.validated_data['approved'],
                processed_by=request.user,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(updated_order).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    @transaction.atomic
    def cancel_order(self, request, pk=None):
        """
        Permite a los clientes cancelar sus órdenes.
        POST /api/v1/marketplace/orders/{id}/cancel/

        Restricciones:
        - Solo el dueño puede cancelar su orden
        - No se pueden cancelar órdenes SHIPPED, DELIVERED, REFUNDED, o ya CANCELLED
        - Para PAID/PREPARING: devuelve el stock al inventario
        - Para PENDING_PAYMENT: libera la reserva
        """
        order = self.get_object()

        # Solo el dueño puede cancelar su propia orden (admins pueden cancelar cualquiera)
        if order.user != request.user and getattr(request.user, 'role', None) != CustomUser.Role.ADMIN:
            return Response(
                {"error": "No tienes permisos para cancelar esta orden."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Validar que se puede cancelar según el estado actual
        CANCELLABLE_STATUSES = {
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.PAID,
            Order.OrderStatus.PREPARING,
        }

        if order.status not in CANCELLABLE_STATUSES:
            return Response(
                {
                    "error": f"No se puede cancelar una orden en estado {order.status}.",
                    "code": "MKT-ORDER-CANCEL-INVALID-STATUS",
                    "current_status": order.status
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.status == Order.OrderStatus.CANCELLED:
            return Response(
                {"error": "La orden ya está cancelada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Guardar estado anterior para logging
        previous_status = order.status

        try:
            # Verificar si necesitamos generar crédito (órdenes ya pagadas)
            should_generate_credit = previous_status in {Order.OrderStatus.PAID, Order.OrderStatus.PREPARING}

            # Si la orden está PAID o PREPARING, necesitamos devolver el stock
            if previous_status in {Order.OrderStatus.PAID, Order.OrderStatus.PREPARING}:
                # Devolver stock al inventario
                for item in order.items.select_related('variant').select_for_update():
                    variant = item.variant
                    variant.stock += item.quantity
                    variant.save(update_fields=['stock'])

                    # Registrar movimiento de inventario
                    InventoryMovement.objects.create(
                        variant=variant,
                        reference_order=order,
                        movement_type=InventoryMovement.MovementType.RETURN,
                        quantity=item.quantity,
                        description=f"Devolución por cancelación de orden {order.id}",
                        created_by=request.user
                    )

            # Usar el servicio para transicionar a CANCELLED
            from ..services import OrderService
            OrderService.transition_to(order, Order.OrderStatus.CANCELLED, changed_by=request.user)

            # Generar crédito si la orden ya fue pagada (PAID o PREPARING)
            credit_amount = Decimal('0')
            if should_generate_credit:
                from finances.services import CreditManagementService

                credit_amount, created_credits = CreditManagementService.issue_credit_from_order(
                    order=order,
                    created_by=request.user if getattr(request.user, 'role', None) == CustomUser.Role.ADMIN else None,
                    reason=f"Crédito por cancelación de orden {order.id} en estado {previous_status}"
                )

                if credit_amount > 0:
                    logger.info(
                        "Crédito generado por cancelación: order_id=%s, user=%s, amount=%s, credits_count=%d",
                        order.id, request.user.id, credit_amount, len(created_credits)
                    )

            logger.info(
                "Orden cancelada por usuario: order_id=%s, user=%s, previous_status=%s, credit_generated=%s",
                order.id, request.user.id, previous_status, credit_amount
            )

            # Retornar la orden actualizada con información de crédito
            serializer = self.get_serializer(order)
            response_data = serializer.data

            # Agregar información de crédito generado si existe
            if credit_amount > 0:
                response_data['credit_generated'] = {
                    'amount': str(credit_amount),
                    'message': f'Se ha generado un crédito de ${credit_amount} para usar en futuras compras.'
                }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(
                "Error al cancelar orden: order_id=%s, user=%s, error=%s",
                order.id, request.user.id, str(e)
            )
            return Response(
                {"error": f"Error al cancelar la orden: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """
        Permite a los clientes eliminar órdenes en estado PENDING_PAYMENT.
        Libera el stock reservado al eliminar la orden.
        """
        order = self.get_object()

        # Solo el dueño puede eliminar su propia orden (get_queryset ya filtra esto para clientes)
        if order.user != request.user and getattr(request.user, 'role', None) != CustomUser.Role.ADMIN:
            return Response(
                {"error": "No tienes permisos para eliminar esta orden."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Solo se pueden eliminar órdenes en estado PENDING_PAYMENT
        if order.status != Order.OrderStatus.PENDING_PAYMENT:
            return Response(
                {
                    "error": f"Solo se pueden eliminar órdenes en estado PENDING_PAYMENT. Estado actual: {order.status}.",
                    "code": "MKT-ORDER-DELETE-INVALID-STATUS"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Liberar stock reservado antes de eliminar
        from ..services import OrderService
        OrderService.release_reservation(
            order,
            movement_type=InventoryMovement.MovementType.RESERVATION_RELEASE,
            reason="Reserva liberada por eliminación de orden",
            changed_by=request.user
        )

        # Guardar info para logging antes de eliminar
        order_id = order.id
        order_status = order.status

        # Eliminar la orden
        order.delete()

        logger.info(
            "Orden eliminada: order_id=%s, user=%s, status=%s",
            order_id, request.user.id, order_status
        )

        return Response(status=status.HTTP_204_NO_CONTENT)

