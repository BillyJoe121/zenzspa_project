from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from marketplace.models import ProductVariant
from spa.models import Appointment, Service

from .formatting import _clean_text, _format_money
CustomUser = get_user_model()


class DataContextService:
    """
    Extrae y formatea la información del negocio en tiempo real
    para inyectarla en el prompt del LLM.
    """

    @staticmethod
    def get_services_context() -> str:
        cache_key = "bot_context:services"
        cached = cache.get(cache_key)
        if cached:
            return cached

        services = Service.objects.filter(is_active=True).order_by("name")
        if not services.exists():
            result = "No hay servicios activos en este momento."
        else:
            lines = []
            for s in services:
                price = _format_money(s.price)
                desc_raw = s.description or ""
                desc = _clean_text(desc_raw[:150] + ("..." if len(desc_raw) > 150 else ""))
                name = _clean_text(s.name)
                lines.append(f"- {name} ({s.duration}min): {price}. {desc}")
            result = "\n".join(lines)

        cache.set(cache_key, result, timeout=300)
        return result

    @staticmethod
    def get_products_context() -> str:
        cache_key = "bot_context:products"
        cached = cache.get(cache_key)
        if cached:
            return cached

        variants = (
            ProductVariant.objects.select_related("product").filter(product__is_active=True).order_by("-stock")[:10]
        )

        if not variants.exists():
            result = "No hay productos publicados actualmente."
        else:
            lines = []
            for v in variants:
                price = _format_money(v.price)
                stock_msg = f"Stock disponible: {v.stock}" if v.stock > 0 else "Actualmente agotado, pronto reabastecemos."
                lines.append(
                    f"- {_clean_text(v.product.name)} ({_clean_text(v.name)}): {price} | {_clean_text(stock_msg)}"
                )
            result = "\n".join(lines)

        cache.set(cache_key, result, timeout=300)
        return result

    @staticmethod
    def get_staff_context() -> str:
        cache_key = "bot_context:staff"
        cached = cache.get(cache_key)
        if cached:
            return cached

        staff = CustomUser.objects.filter(role=CustomUser.Role.STAFF, is_active=True)[:5]
        if not staff.exists():
            result = "Equipo de terapeutas expertos."
        else:
            result = "\n".join([f"- {_clean_text(person.get_full_name())}" for person in staff])

        cache.set(cache_key, result, timeout=300)
        return result

    @staticmethod
    def get_client_context(user) -> str:
        if not user or not user.is_authenticated:
            return "Cliente Visitante (No logueado)"

        now = timezone.now()
        upcoming = (
            Appointment.objects.filter(
                user=user,
                start_time__gte=now,
                status__in=["CONFIRMED", "PENDING_PAYMENT"],
            )
            .order_by("start_time")
            .first()
        )

        appt_info = "Sin citas próximas agendadas."
        if upcoming:
            local_time = timezone.localtime(upcoming.start_time).strftime("%d/%m a las %H:%M")
            services = upcoming.get_service_names() or "servicios personalizados"
            appt_info = f"Tiene una cita próxima: {_clean_text(services)} el {local_time}."

        is_vip = getattr(user, "is_vip", False)
        first_name_only = _clean_text(user.first_name if hasattr(user, "first_name") else "Cliente")
        return f"""
        Cliente: {first_name_only}
        Estado VIP: {'Sí' if is_vip else 'No'}
        {_clean_text(appt_info)}
        """


__all__ = ["DataContextService"]
