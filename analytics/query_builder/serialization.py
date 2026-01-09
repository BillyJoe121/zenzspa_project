"""
Query Builder - Serialización de resultados.
"""
from users.models import CustomUser
from spa.models import Appointment, Service
from finances.models import Payment
from marketplace.models import Order


class QueryBuilderSerializationMixin:
    """Serialización de resultados para cada entidad."""

    def _serialize_results(self, objects: list) -> list[dict]:
        """Serializa los resultados según la entidad."""
        serializer = getattr(self, f"_serialize_{self.entity_key}", self._serialize_generic)
        return [serializer(obj) for obj in objects]

    def _serialize_clients(self, obj: CustomUser) -> dict:
        """Serializa un cliente."""
        return {
            "id": str(obj.id),
            "phone_number": obj.phone_number,
            "email": obj.email or "",
            "first_name": obj.first_name or "",
            "last_name": obj.last_name or "",
            "full_name": obj.get_full_name(),
            "role": obj.role,
            "is_vip": obj.is_vip,
            "vip_expires_at": obj.vip_expires_at.isoformat() if obj.vip_expires_at else None,
            "date_joined": obj.created_at.isoformat() if obj.created_at else None,
            "is_persona_non_grata": obj.is_persona_non_grata,
            "last_appointment_date": getattr(obj, "last_appointment_date", None),
            "total_appointments": getattr(obj, "total_appointments", 0),
            "completed_appointments": getattr(obj, "completed_appointments", 0),
            "total_spent": float(getattr(obj, "total_spent", 0) or 0),
        }

    def _serialize_appointments(self, obj: Appointment) -> dict:
        """Serializa una cita."""
        return {
            "id": str(obj.id),
            "date": obj.start_time.isoformat() if obj.start_time else None,
            "start_time": obj.start_time.isoformat() if obj.start_time else None,
            "status": obj.status,
            "outcome": obj.outcome,
            "total_amount": float(obj.price_at_purchase or 0),
            "client": {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name(),
                "phone": obj.user.phone_number,
            } if obj.user else None,
            "staff": {
                "id": str(obj.staff_member.id),
                "name": obj.staff_member.get_full_name(),
            } if obj.staff_member else None,
            "reschedule_count": obj.reschedule_count,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
        }

    def _serialize_payments(self, obj: Payment) -> dict:
        """Serializa un pago."""
        return {
            "id": str(obj.id),
            "amount": float(obj.amount or 0),
            "status": obj.status,
            "payment_type": obj.payment_type,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "client": {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name(),
                "phone": obj.user.phone_number,
            } if obj.user else None,
            "wompi_reference": obj.wompi_reference or "",
        }

    def _serialize_orders(self, obj: Order) -> dict:
        """Serializa una orden."""
        return {
            "id": str(obj.id),
            "status": obj.status,
            "total_amount": float(obj.total_amount or 0),
            "shipping_cost": float(obj.shipping_cost or 0),
            "delivery_option": obj.delivery_option,
            "delivery_address": obj.delivery_address or "",
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "client": {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name(),
                "phone": obj.user.phone_number,
            } if obj.user else None,
        }

    def _serialize_services(self, obj: Service) -> dict:
        """Serializa un servicio."""
        return {
            "id": str(obj.id),
            "name": obj.name,
            "description": obj.description[:200] if obj.description else "",
            "price": float(obj.price or 0),
            "vip_price": float(obj.vip_price or 0) if obj.vip_price else None,
            "duration": obj.duration,
            "is_active": obj.is_active,
            "category": obj.category.name if obj.category else None,
        }

    def _serialize_generic(self, obj) -> dict:
        """Serialización genérica para cualquier modelo."""
        return {
            "id": str(obj.id) if hasattr(obj, "id") else None,
            "created_at": obj.created_at.isoformat() if hasattr(obj, "created_at") and obj.created_at else None,
        }
