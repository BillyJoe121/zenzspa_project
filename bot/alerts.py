"""
Servicio de alertas y notificaciones para actividades sospechosas.
Envía notificaciones a los administradores cuando se detectan amenazas críticas.
Migrado al sistema centralizado de NotificationService.
"""
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db import models
from notifications.services import NotificationService

logger = logging.getLogger(__name__)


class SuspiciousActivityAlertService:
    """
    Servicio para enviar alertas cuando se detectan actividades sospechosas críticas.
    """

    @staticmethod
    def send_critical_activity_alert(suspicious_activity):
        """
        Envía una alerta por WhatsApp y Email cuando se detecta una actividad crítica.
        Migrado al sistema centralizado de NotificationService.

        Args:
            suspicious_activity: Instancia de SuspiciousActivity
        """
        from .models import BotConfiguration
        from users.models import CustomUser

        try:
            # Verificar si las alertas están habilitadas
            config = BotConfiguration.objects.filter(is_active=True).first()
            if not config or not getattr(config, 'enable_critical_alerts', True):
                logger.info("Alertas críticas deshabilitadas en configuración")
                return

            # Obtener configuración del admin
            admin_phone = config.admin_phone if config else None

            if not admin_phone:
                logger.warning("No hay teléfono de admin configurado para alertas de seguridad")
                return

            # Buscar usuario admin con ese teléfono
            admin_user = CustomUser.objects.filter(
                phone_number=admin_phone,
                is_staff=True,
                is_active=True
            ).first()

            if not admin_user:
                # Fallback: buscar cualquier admin activo
                admin_user = CustomUser.objects.filter(
                    models.Q(is_superuser=True) | models.Q(role=CustomUser.Role.ADMIN),
                    is_active=True
                ).first()

            if not admin_user:
                logger.warning("No se encontró usuario admin para enviar alerta de seguridad")
                return

            # Preparar contexto
            context = {
                "alert_type": suspicious_activity.get_activity_type_display(),
                "user_identifier": suspicious_activity.participant_identifier or suspicious_activity.ip_address,
                "alert_detail": suspicious_activity.description,
                "timestamp": suspicious_activity.created_at.strftime("%d/%m/%Y %H:%M:%S") if suspicious_activity.created_at else timezone.now().strftime("%d/%m/%Y %H:%M:%S"),
            }

            # Enviar notificación usando el sistema centralizado
            NotificationService.send_notification(
                user=admin_user,
                event_code="BOT_SECURITY_ALERT",
                context=context,
                priority="critical"  # Critical para ignorar quiet hours
            )

            logger.info(
                "Alerta de seguridad enviada para actividad %d (IP: %s)",
                suspicious_activity.id, suspicious_activity.ip_address
            )

        except Exception as e:
            # No fallar el proceso principal si la notificación falla
            logger.error("Error enviando alerta de seguridad: %s", e, exc_info=True)

    @staticmethod
    def send_auto_block_notification(ip_address, reason, critical_count, block_id):
        """
        Envía notificación cuando una IP es bloqueada automáticamente.
        Migrado al sistema centralizado de NotificationService.

        Args:
            ip_address: IP bloqueada
            reason: Razón del bloqueo
            critical_count: Número de actividades críticas
            block_id: ID del registro de bloqueo
        """
        from .models import BotConfiguration
        from users.models import CustomUser

        try:
            # Obtener configuración del admin
            config = BotConfiguration.objects.filter(is_active=True).first()
            admin_phone = config.admin_phone if config else None

            if not admin_phone:
                logger.warning("No hay teléfono de admin configurado para notificar auto-bloqueo")
                return

            # Buscar usuario admin con ese teléfono
            admin_user = CustomUser.objects.filter(
                phone_number=admin_phone,
                is_staff=True,
                is_active=True
            ).first()

            if not admin_user:
                # Fallback: buscar cualquier admin activo
                admin_user = CustomUser.objects.filter(
                    models.Q(is_superuser=True) | models.Q(role=CustomUser.Role.ADMIN),
                    is_active=True
                ).first()

            if not admin_user:
                logger.warning("No se encontró usuario admin para notificar auto-bloqueo")
                return

            # Preparar contexto
            context = {
                "user_identifier": ip_address or "IP desconocida",
                "block_reason": reason or "Actividades sospechosas",
                "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                "admin_url": f"{settings.SITE_URL.rstrip('/')}/admin/bot/ipblocklist/{block_id}/change/",
            }

            # Enviar notificación usando el sistema centralizado
            NotificationService.send_notification(
                user=admin_user,
                event_code="BOT_AUTO_BLOCK",
                context=context,
                priority="critical"  # Critical para ignorar quiet hours
            )

            logger.info(
                "Notificación de auto-bloqueo enviada para IP %s",
                ip_address
            )

        except Exception as e:
            logger.error("Error enviando notificación de auto-bloqueo: %s", e, exc_info=True)

    @staticmethod
    def send_daily_security_report():
        """
        Envía un reporte diario de seguridad con estadísticas via WhatsApp.
        """
        from .models import SuspiciousActivity, IPBlocklist, BotConversationLog, BotConfiguration
        from django.db.models import Count, Q
        from users.models import CustomUser

        try:
            config = BotConfiguration.objects.filter(is_active=True).first()
            admin_phone = config.admin_phone if config else None

            if not admin_phone:
                logger.warning("No hay teléfono de admin configurado para el reporte diario de seguridad")
                return

            admin_user = CustomUser.objects.filter(
                phone_number=admin_phone,
                is_staff=True,
                is_active=True
            ).first()

            if not admin_user:
                admin_user = CustomUser.objects.filter(
                    models.Q(is_superuser=True) | models.Q(role=CustomUser.Role.ADMIN),
                    is_active=True
                ).first()

            if not admin_user:
                logger.warning("No se encontró usuario admin para enviar el reporte diario de seguridad")
                return

            yesterday = timezone.now() - timedelta(hours=24)

            activities = SuspiciousActivity.objects.filter(created_at__gte=yesterday)
            total_activities = activities.count()
            critical_activities = activities.filter(severity=SuspiciousActivity.SeverityLevel.CRITICAL).count()
            high_activities = activities.filter(severity=SuspiciousActivity.SeverityLevel.HIGH).count()

            new_blocks = IPBlocklist.objects.filter(created_at__gte=yesterday).count()

            conversations = BotConversationLog.objects.filter(created_at__gte=yesterday)
            total_conversations = conversations.count()
            blocked_conversations = conversations.filter(was_blocked=True).count()

            top_ips = activities.values('ip_address').annotate(
                count=Count('id')
            ).order_by('-count')[:5]

            report_lines = [
                f"Período: {yesterday.strftime('%Y-%m-%d %H:%M')} - {timezone.now().strftime('%Y-%m-%d %H:%M')}",
                f"Conversaciones: {total_conversations} (bloqueadas {blocked_conversations})",
                f"Actividades sospechosas: {total_activities} (críticas {critical_activities}, altas {high_activities})",
                f"Nuevas IPs bloqueadas: {new_blocks}",
                "Top IPs:",
            ]
            for idx, ip_data in enumerate(top_ips, 1):
                report_lines.append(f"{idx}. {ip_data['ip_address']}: {ip_data['count']} eventos")

            alert_detail = "\n".join(report_lines)

            NotificationService.send_notification(
                user=admin_user,
                event_code="BOT_SECURITY_ALERT",
                context={
                    "alert_type": "Reporte diario de seguridad",
                    "user_identifier": admin_user.phone_number or admin_user.email or "admin",
                    "alert_detail": alert_detail,
                    "timestamp": timezone.now().strftime("%d/%m/%Y %H:%M:%S"),
                },
                priority="high",
            )

            logger.info("Reporte diario de seguridad enviado vía WhatsApp")

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
