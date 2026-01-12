"""
Query Builder - Opciones de selección.
"""
USER_ROLE_OPTIONS = [
    {"value": "CLIENT", "label": "Cliente"},
    {"value": "VIP", "label": "VIP"},
    {"value": "STAFF", "label": "Staff"},
    {"value": "ADMIN", "label": "Administrador"},
]

APPOINTMENT_STATUS_OPTIONS = [
    {"value": "PENDING_PAYMENT", "label": "Pendiente de Pago"},
    {"value": "PAID", "label": "Pagado"},
    {"value": "CONFIRMED", "label": "Confirmada"},
    {"value": "RESCHEDULED", "label": "Reagendada"},
    {"value": "COMPLETED", "label": "Completada"},
    {"value": "CANCELLED", "label": "Cancelada"},
]

APPOINTMENT_OUTCOME_OPTIONS = [
    {"value": "NONE", "label": "Sin resultado"},
    {"value": "CANCELLED_BY_CLIENT", "label": "Cancelada por Cliente"},
    {"value": "CANCELLED_BY_SYSTEM", "label": "Cancelada por Sistema"},
    {"value": "CANCELLED_BY_ADMIN", "label": "Cancelada por Admin"},
    {"value": "NO_SHOW", "label": "No Asistió"},
    {"value": "REFUNDED", "label": "Reembolsada"},
]

PAYMENT_STATUS_OPTIONS = [
    {"value": "PENDING", "label": "Pendiente"},
    {"value": "APPROVED", "label": "Aprobado"},
    {"value": "DECLINED", "label": "Declinado"},
    {"value": "ERROR", "label": "Error"},
    {"value": "TIMEOUT", "label": "Sin confirmación"},
]

PAYMENT_TYPE_OPTIONS = [
    {"value": "ADVANCE", "label": "Anticipo de Cita"},
    {"value": "FINAL", "label": "Pago Final"},
    {"value": "PACKAGE", "label": "Compra de Paquete"},
    {"value": "TIP", "label": "Propina"},
    {"value": "VIP_SUBSCRIPTION", "label": "Membresía VIP"},
    {"value": "ORDER", "label": "Orden Marketplace"},
]

ORDER_STATUS_OPTIONS = [
    {"value": "PENDING_PAYMENT", "label": "Pendiente de Pago"},
    {"value": "PAID", "label": "Pagada"},
    {"value": "PREPARING", "label": "En Preparación"},
    {"value": "SHIPPED", "label": "Enviada"},
    {"value": "DELIVERED", "label": "Entregada"},
    {"value": "CANCELLED", "label": "Cancelada"},
    {"value": "RETURN_REQUESTED", "label": "Devolución Solicitada"},
    {"value": "REFUNDED", "label": "Reembolsada"},
]

DELIVERY_OPTIONS = [
    {"value": "PICKUP", "label": "Recogida en Local"},
    {"value": "DELIVERY", "label": "Envío a Domicilio"},
]
