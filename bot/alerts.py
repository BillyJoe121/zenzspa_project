"""
Servicio de alertas y notificaciones para actividades sospechosas.
Envía emails a los administradores cuando se detectan amenazas críticas.
"""
import logging
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db import models

logger = logging.getLogger(__name__)


class SuspiciousActivityAlertService:
    """
    Servicio para enviar alertas cuando se detectan actividades sospechosas críticas.
    """

    @staticmethod
    def get_admin_emails():
        """
        Obtiene la lista de emails de administradores que deben recibir alertas.
        """
        from users.models import CustomUser

        # Obtener todos los ADMIN y SUPERUSERS
        admins = CustomUser.objects.filter(
            is_active=True
        ).filter(
            models.Q(is_superuser=True) | models.Q(role=CustomUser.Role.ADMIN)
        )

        emails = [admin.email for admin in admins if admin.email]

        # Si no hay emails configurados, usar el DEFAULT_FROM_EMAIL de settings
        if not emails and hasattr(settings, 'ADMINS'):
            emails = [email for name, email in settings.ADMINS]

        return emails

    @staticmethod
    def send_critical_activity_alert(suspicious_activity):
        """
        Envía una alerta por email cuando se detecta una actividad crítica.

        Args:
            suspicious_activity: Instancia de SuspiciousActivity
        """
        from .models import BotConfiguration

        try:
            # Verificar si las alertas están habilitadas
            config = BotConfiguration.objects.filter(is_active=True).first()
            if not config or not getattr(config, 'enable_critical_alerts', True):
                logger.info("Alertas críticas deshabilitadas en configuración")
                return

            # Obtener emails de administradores
            admin_emails = SuspiciousActivityAlertService.get_admin_emails()

            if not admin_emails:
                logger.warning("No hay emails de administradores configurados para alertas")
                return

            # Preparar contexto para el email
            context = {
                'activity': suspicious_activity,
                'participant': suspicious_activity.participant_identifier,
                'ip_address': suspicious_activity.ip_address,
                'activity_type': suspicious_activity.get_activity_type_display(),
                'severity': suspicious_activity.get_severity_display(),
                'description': suspicious_activity.description,
                'created_at': suspicious_activity.created_at,
                'admin_url': f"{settings.SITE_URL}/admin/bot/suspiciousactivity/{suspicious_activity.id}/change/",
            }

            # Asunto del email
            subject = f"[ALERTA CRÍTICA] {context['activity_type']} - {context['ip_address']}"

            # Cuerpo del email (texto plano)
            message = f"""
⚠️ ALERTA DE SEGURIDAD - ACTIVIDAD CRÍTICA DETECTADA ⚠️

Tipo: {context['activity_type']}
Severidad: {context['severity']}
Usuario/IP: {context['participant']}
IP: {context['ip_address']}
Fecha: {context['created_at'].strftime('%Y-%m-%d %H:%M:%S')}

DESCRIPCIÓN:
{context['description']}

ACCIÓN REQUERIDA:
Por favor, revisa esta actividad inmediatamente en el panel de administración:
{context['admin_url']}

Considera bloquear esta IP si el patrón de abuso continúa.

---
Este es un mensaje automático del sistema de seguridad de Zenzspa Bot.
            """.strip()

            # Enviar email
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                fail_silently=False,
            )

            logger.info(
                "Alerta crítica enviada a %d administrador(es) para actividad %d (IP: %s)",
                len(admin_emails), suspicious_activity.id, suspicious_activity.ip_address
            )

        except Exception as e:
            # No fallar el proceso principal si el email falla
            logger.error("Error enviando alerta crítica por email: %s", e, exc_info=True)

    @staticmethod
    def send_auto_block_notification(ip_address, reason, critical_count, block_id):
        """
        Envía notificación cuando una IP es bloqueada automáticamente.

        Args:
            ip_address: IP bloqueada
            reason: Razón del bloqueo
            critical_count: Número de actividades críticas
            block_id: ID del registro de bloqueo
        """
        try:
            admin_emails = SuspiciousActivityAlertService.get_admin_emails()

            if not admin_emails:
                logger.warning("No hay emails de administradores para notificar auto-bloqueo")
                return

            subject = f"[AUTO-BLOQUEO] IP {ip_address} bloqueada automáticamente"

            message = f"""
🚫 BLOQUEO AUTOMÁTICO DE IP 🚫

La IP {ip_address} ha sido bloqueada automáticamente por el sistema de seguridad.

Razón: {reason}
Actividades críticas detectadas: {critical_count}
Fecha: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}

Esta IP ha alcanzado el umbral de actividades críticas y ha sido bloqueada preventivamente.

Ver detalles del bloqueo:
{settings.SITE_URL}/admin/bot/ipblocklist/{block_id}/change/

Ver actividades de esta IP:
{settings.SITE_URL}/admin/bot/suspiciousactivity/?ip_address={ip_address}

Si consideras que el bloqueo es incorrecto, puedes desactivarlo desde el panel de administración.

---
Este es un mensaje automático del sistema de seguridad de Zenzspa Bot.
            """.strip()

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                fail_silently=False,
            )

            logger.info(
                "Notificación de auto-bloqueo enviada a %d administrador(es) para IP %s",
                len(admin_emails), ip_address
            )

        except Exception as e:
            logger.error("Error enviando notificación de auto-bloqueo: %s", e, exc_info=True)

    @staticmethod
    def send_daily_security_report():
        """
        Envía un reporte diario de seguridad con estadísticas.
        Este método puede ser llamado por un Celery task diario.
        """
        from .models import SuspiciousActivity, IPBlocklist, BotConversationLog
        from django.db.models import Count, Q

        try:
            admin_emails = SuspiciousActivityAlertService.get_admin_emails()

            if not admin_emails:
                return

            # Estadísticas de las últimas 24 horas
            yesterday = timezone.now() - timedelta(hours=24)

            # Actividades sospechosas
            activities = SuspiciousActivity.objects.filter(created_at__gte=yesterday)
            total_activities = activities.count()
            critical_activities = activities.filter(severity=SuspiciousActivity.SeverityLevel.CRITICAL).count()
            high_activities = activities.filter(severity=SuspiciousActivity.SeverityLevel.HIGH).count()

            # IPs bloqueadas
            new_blocks = IPBlocklist.objects.filter(created_at__gte=yesterday).count()

            # Conversaciones
            conversations = BotConversationLog.objects.filter(created_at__gte=yesterday)
            total_conversations = conversations.count()
            blocked_conversations = conversations.filter(was_blocked=True).count()

            # Top 5 IPs con más actividad sospechosa
            top_ips = activities.values('ip_address').annotate(
                count=Count('id')
            ).order_by('-count')[:5]

            subject = f"[Reporte Diario] Seguridad del Bot - {timezone.now().strftime('%Y-%m-%d')}"

            message = f"""
📊 REPORTE DIARIO DE SEGURIDAD - ZENZSPA BOT 📊
Período: {yesterday.strftime('%Y-%m-%d %H:%M')} - {timezone.now().strftime('%Y-%m-%d %H:%M')}

═══════════════════════════════════════════════════

📈 CONVERSACIONES:
- Total de conversaciones: {total_conversations}
- Conversaciones bloqueadas: {blocked_conversations}
- Tasa de bloqueo: {(blocked_conversations/total_conversations*100) if total_conversations > 0 else 0:.2f}%

⚠️ ACTIVIDADES SOSPECHOSAS:
- Total detectadas: {total_activities}
- Críticas: {critical_activities}
- Altas: {high_activities}

🚫 BLOQUEOS:
- Nuevas IPs bloqueadas: {new_blocks}

🔝 TOP 5 IPs CON MÁS ACTIVIDAD SOSPECHOSA:
"""
            for idx, ip_data in enumerate(top_ips, 1):
                message += f"{idx}. {ip_data['ip_address']}: {ip_data['count']} actividades\n"

            message += f"""

═══════════════════════════════════════════════════

Ver panel de administración:
{settings.SITE_URL}/admin/bot/suspiciousactivity/

---
Este es un reporte automático del sistema de seguridad.
            """

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                fail_silently=False,
            )

            logger.info("Reporte diario de seguridad enviado a %d administrador(es)", len(admin_emails))

        except Exception as e:
            logger.error("Error enviando reporte diario de seguridad: %s", e, exc_info=True)


class AutoBlockService:
    """
    Servicio para auto-bloqueo de IPs con comportamiento abusivo.
    """

    @staticmethod
    def check_and_auto_block(user=None, anonymous_user=None, ip_address=None):
        """
        Verifica si un usuario/IP ha alcanzado el umbral de actividades críticas
        y lo bloquea automáticamente si es necesario.

        Args:
            user: Usuario registrado (opcional)
            anonymous_user: Usuario anónimo (opcional)
            ip_address: IP del usuario

        Returns:
            tuple: (was_blocked: bool, block: IPBlocklist or None)
        """
        from .models import SuspiciousActivity, IPBlocklist, BotConfiguration
        from django.db.models import Count, Q

        try:
            # Obtener configuración
            config = BotConfiguration.objects.filter(is_active=True).first()
            if not config:
                return False, None

            # Verificar si el auto-bloqueo está habilitado
            auto_block_enabled = getattr(config, 'enable_auto_block', True)
            if not auto_block_enabled:
                return False, None

            # Umbral de actividades críticas (default: 3)
            critical_threshold = getattr(config, 'auto_block_critical_threshold', 3)

            # Período de análisis en horas (default: 24 horas)
            analysis_period_hours = getattr(config, 'auto_block_analysis_period_hours', 24)
            since = timezone.now() - timedelta(hours=analysis_period_hours)

            # Verificar si la IP ya está bloqueada
            if ip_address:
                existing_block = IPBlocklist.objects.filter(
                    ip_address=ip_address,
                    is_active=True
                ).first()

                if existing_block and existing_block.is_effective:
                    # Ya está bloqueada
                    return False, existing_block

            # Construir filtro para actividades
            activity_filter = Q(created_at__gte=since)

            if user:
                activity_filter &= Q(user=user)
            elif anonymous_user:
                activity_filter &= Q(anonymous_user=anonymous_user)

            if ip_address:
                activity_filter &= Q(ip_address=ip_address)

            # Contar actividades críticas
            critical_count = SuspiciousActivity.objects.filter(
                activity_filter,
                severity=SuspiciousActivity.SeverityLevel.CRITICAL
            ).count()

            logger.info(
                "Auto-block check: IP=%s, critical_count=%d, threshold=%d",
                ip_address, critical_count, critical_threshold
            )

            # Si alcanzó el umbral, bloquear
            if critical_count >= critical_threshold:
                # Crear bloqueo automático
                block = IPBlocklist.objects.create(
                    ip_address=ip_address,
                    reason=IPBlocklist.BlockReason.ABUSE,
                    notes=f"Auto-bloqueado por el sistema: {critical_count} actividades críticas "
                          f"en las últimas {analysis_period_hours} horas. "
                          f"Umbral: {critical_threshold}.",
                    blocked_by=None,  # Sistema
                    expires_at=None,  # Permanente por defecto
                    is_active=True
                )

                logger.warning(
                    "IP %s auto-bloqueada: %d actividades críticas (umbral: %d)",
                    ip_address, critical_count, critical_threshold
                )

                # Enviar notificación
                SuspiciousActivityAlertService.send_auto_block_notification(
                    ip_address=ip_address,
                    reason="Múltiples actividades críticas detectadas",
                    critical_count=critical_count,
                    block_id=block.id
                )

                return True, block

            return False, None

        except Exception as e:
            logger.error("Error en check_and_auto_block: %s", e, exc_info=True)
            return False, None
