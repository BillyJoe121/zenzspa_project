from datetime import datetime, timedelta
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

from spa.models import Appointment, Service
from spa.services import AppointmentService, AvailabilityService

logger = logging.getLogger(__name__)
CustomUser = get_user_model()


class GeminiService:
    """
    Pequeño wrapper alrededor del modelo generativo (Gemini) para centralizar
    la llamada y el post-procesamiento. Por ahora simula la respuesta.
    """

    def __init__(self, client=None):
        self.client = client

    def generate_response(self, message, user=None):
        """
        Retorna una estructura con el texto que verá el usuario y posibles
        acciones que la IA considera relevantes.
        """
        logger.debug("Gemini prompt: %s", message)
        # En producción se llamaría a google-generativeai aquí. Se deja simulado.
        suggested_actions = []
        normalized_message = (message or "").lower()
        if "agenda" in normalized_message:
            suggested_actions.append({"type": "BOOK_APPOINTMENT"})
        if "cancel" in normalized_message:
            suggested_actions.append({"type": "CANCEL_APPOINTMENT"})
        if "disponibilidad" in normalized_message or "horario" in normalized_message:
            suggested_actions.append({"type": "CHECK_AVAILABILITY"})

        return {
            "reply": f"[Gemini] Entendí tu mensaje: “{message}”. ¿Te gustaría que te ayude con algo más?",
            "suggested_actions": suggested_actions,
        }


class ActionExecutorService:
    """
    Recibe una acción estructurada y la ejecuta usando los servicios del dominio.
    Sirve como guardrail entre la IA y la base de datos.
    """

    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"

    def __init__(self, user):
        self.user = user

    def preview_action(self, action):
        action_type = action.get("type")
        if action_type == self.BOOK_APPOINTMENT:
            services = action.get("service_ids", [])
            start_time = action.get("start_time")
            return {
                "title": "Agendar cita",
                "summary": f"Se reservará {'/'.join(services) or 'los servicios seleccionados'} a las {start_time}.",
            }
        if action_type == self.CANCEL_APPOINTMENT:
            appointment_id = action.get("appointment_id")
            return {
                "title": "Cancelar cita",
                "summary": f"Se cancelará la cita {appointment_id}. Esta acción no se puede deshacer.",
            }
        if action_type == self.CHECK_AVAILABILITY:
            return {
                "title": "Consultar disponibilidad",
                "summary": "Se consultarán horarios libres para los servicios y fecha solicitados.",
            }
        return {"title": "Acción desconocida", "summary": "No se puede obtener la vista previa."}

    def execute_action(self, action):
        action_type = action.get("type")
        if action_type == self.BOOK_APPOINTMENT:
            return self._book_appointment(action)
        if action_type == self.CANCEL_APPOINTMENT:
            return self._cancel_appointment(action)
        if action_type == self.CHECK_AVAILABILITY:
            return self._check_availability(action)
        raise ValueError("Acción no soportada.")

    def _book_appointment(self, action):
        service_ids = action.get("service_ids") or []
        start_time_str = action.get("start_time")
        if not service_ids or not start_time_str:
            raise ValueError("service_ids y start_time son obligatorios.")

        services = list(Service.objects.filter(id__in=service_ids, is_active=True))
        if len(services) != len(set(service_ids)):
            raise ValueError("Uno o más servicios son inválidos o están inactivos.")

        staff_member = None
        staff_member_id = action.get("staff_member_id")
        if staff_member_id:
            try:
                staff_member = CustomUser.objects.get(id=staff_member_id)
            except CustomUser.DoesNotExist:
                raise ValueError("El miembro de staff indicado no existe.")

        try:
            start_time = datetime.fromisoformat(start_time_str)
        except ValueError as exc:
            raise ValueError("start_time debe estar en formato ISO 8601.") from exc

        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time, timezone.get_current_timezone())

        appointment_service = AppointmentService(
            user=self.user,
            services=services,
            staff_member=staff_member,
            start_time=start_time,
        )
        appointment = appointment_service.create_appointment_with_lock()
        return {
            "status": "success",
            "appointment_id": str(appointment.id),
            "start_time": appointment.start_time.isoformat(),
        }

    def _cancel_appointment(self, action):
        appointment_id = action.get("appointment_id")
        if not appointment_id:
            raise ValueError("appointment_id es obligatorio.")
        try:
            appointment = Appointment.objects.get(id=appointment_id, user=self.user)
        except Appointment.DoesNotExist:
            raise ValueError("No se encontró la cita indicada.")

        appointment.status = Appointment.AppointmentStatus.CANCELLED_BY_CLIENT
        appointment.save(update_fields=["status", "updated_at"])
        return {"status": "success", "appointment_id": str(appointment.id)}

    def _check_availability(self, action):
        service_ids = action.get("service_ids") or []
        if not service_ids:
            raise ValueError("Debes especificar los servicios a consultar.")

        services = list(Service.objects.filter(id__in=service_ids, is_active=True))
        if len(services) != len(set(service_ids)):
            raise ValueError("Alguno de los servicios solicitados no existe o está inactivo.")

        date_str = action.get("date")
        date_text = action.get("date_text")
        target_date = self._parse_natural_date(date_str or date_text)

        staff_id = action.get("staff_member_id")
        slots = AvailabilityService.get_available_slots(
            target_date,
            [str(s.id) for s in services],
            staff_member_id=staff_id,
        )
        formatted = [
            {
                "start_time": slot["start_time"].isoformat()
                if hasattr(slot["start_time"], "isoformat")
                else slot["start_time"],
                "staff_id": slot["staff_id"],
                "staff_name": slot["staff_name"],
            }
            for slot in slots
        ]
        return {
            "status": "success",
            "date": target_date.isoformat(),
            "slots": formatted,
        }

    def _parse_natural_date(self, text):
        today = timezone.localdate()
        if not text:
            return today
        normalized = text.strip().lower()
        if normalized in ("hoy", "today"):
            return today
        if normalized in ("mañana", "tomorrow"):
            return today + timedelta(days=1)
        if normalized in ("pasado mañana", "the day after tomorrow"):
            return today + timedelta(days=2)

        weekdays = {
            "lunes": 0,
            "martes": 1,
            "miércoles": 2,
            "miercoles": 2,
            "jueves": 3,
            "viernes": 4,
            "sábado": 5,
            "sabado": 5,
            "domingo": 6,
        }
        for keyword, weekday in weekdays.items():
            if keyword in normalized:
                days_ahead = (weekday - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                return today + timedelta(days=days_ahead)

        try:
            return datetime.fromisoformat(text).date()
        except (TypeError, ValueError):
            raise ValueError("No se pudo interpretar la fecha solicitada.")
