"""
Sistema de notificaciones para escalamiento humano.
Envía notificaciones por email a staff y admin cuando se crea un handoff request.
Migrado al sistema centralizado de NotificationService.
"""
import logging
from django.conf import settings
from notifications.services import NotificationService

logger = logging.getLogger(__name__)


class HandoffNotificationService:
    """
    Servicio para enviar notificaciones de handoff a staff y admin.
    """

    @staticmethod
    def send_handoff_notification(handoff_request):
        """
        Envía notificación por WhatsApp y Email a staff/admin sobre un nuevo handoff.
        Migrado al sistema centralizado de NotificationService.

        Args:
            handoff_request: Instancia de HumanHandoffRequest
        """
        from users.models import CustomUser
        from bot.models import BotConfiguration

        # Obtener configuración del bot para el teléfono del admin
        bot_config = BotConfiguration.objects.filter(is_active=True).first()
        admin_phone = bot_config.admin_phone if bot_config else None

        if not admin_phone:
            logger.warning("No hay teléfono de admin configurado para handoff %d", handoff_request.id)
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
                role=CustomUser.Role.ADMIN,
                is_active=True
            ).first()

        if not admin_user:
            logger.warning("No se encontró usuario admin para enviar notificación de handoff %d", handoff_request.id)
            return

        # Determinar emoji según score
        score_emoji = "🟢"
        if handoff_request.client_score >= 70:
            score_emoji = "🔴"  # Alta prioridad
        elif handoff_request.client_score >= 40:
            score_emoji = "🟡"  # Media prioridad

        # Alerta de toxicidad
        sexual_score = handoff_request.conversation_context.get('sexual_score', 0)
        warning_text = ""
        if sexual_score > 0:
            warning_text = "⚠️ ALERTA: Cliente ha hecho comentarios inapropiados."

        # Preparar contexto para NotificationService
        context = {
            "score_emoji": score_emoji,
            "client_score": str(handoff_request.client_score),
            "client_name": handoff_request.client_contact_info.get('name', 'Anónimo'),
            "client_phone": handoff_request.client_contact_info.get('phone', 'N/A'),
            "warning_text": warning_text,
            "escalation_message": handoff_request.conversation_context.get('escalation_message', 'No disponible'),
            "admin_url": f"{settings.SITE_URL}/admin/bot/humanhandoffrequest/{handoff_request.id}/change/",
        }

        try:
            NotificationService.send_notification(
                user=admin_user,
                event_code="BOT_HANDOFF_CREATED",
                context=context,
                priority="high"
            )
            logger.info("Notificación de handoff %d enviada al admin", handoff_request.id)
        except Exception as e:
            logger.error("Error enviando notificación de handoff %d: %s", handoff_request.id, e)

    @staticmethod
    def _build_html_message(context):
        """Construye el mensaje HTML para el email"""
        handoff = context['handoff']
        client_info = context['client_info']
        score = context['score']
        reason = context['reason']
        interests = context['interests']
        conv_context = context['conversation_context']
        admin_url = context['admin_url']

        # Badge de color según el score
        if score >= 70:
            badge_color = "#28a745"  # Verde
            badge_label = "ALTO VALOR"
        elif score >= 40:
            badge_color = "#ffc107"  # Amarillo
            badge_label = "VALOR MEDIO"
        else:
            badge_color = "#6c757d"  # Gris
            badge_label = "VALOR BAJO"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .badge {{ display: inline-block; padding: 5px 10px; border-radius: 4px; font-weight: bold; font-size: 14px; }}
                .content {{ background: #f8f9fa; padding: 20px; }}
                .section {{ background: white; padding: 15px; margin: 10px 0; border-radius: 4px; border-left: 4px solid #667eea; }}
                .label {{ font-weight: bold; color: #667eea; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 4px; margin: 10px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #6c757d; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">🚨 Nueva Solicitud de Atención Humana</h1>
                    <p style="margin: 10px 0 0 0;">Un cliente solicita hablar con una persona</p>
                </div>

                <div class="content">
                    <div class="section">
                        <p><span class="badge" style="background-color: {badge_color}; color: white;">{badge_label}</span></p>
                        <p><span class="label">Score del Cliente:</span> {score}/100</p>
                        <p><span class="label">Razón:</span> {reason}</p>
                    </div>

                    <div class="section">
                        <h3>👤 Información del Cliente</h3>
                        <p><span class="label">Nombre:</span> {client_info.get('name', 'No proporcionado')}</p>
                        <p><span class="label">Email:</span> {client_info.get('email', 'No proporcionado')}</p>
                        <p><span class="label">Teléfono:</span> {client_info.get('phone', 'No proporcionado')}</p>
                    </div>
        """

        # Agregar intereses si existen
        if interests.get('services_mentioned'):
            services = ', '.join(interests['services_mentioned'])
            html += f"""
                    <div class="section">
                        <h3>💆 Servicios Consultados</h3>
                        <p>{services}</p>
                    </div>
            """

        # Agregar último mensaje
        if conv_context.get('escalation_message'):
            html += f"""
                    <div class="section">
                        <h3>💬 Último Mensaje del Cliente</h3>
                        <p style="font-style: italic;">"{conv_context['escalation_message']}"</p>
                    </div>
            """

        html += f"""
                    <div style="text-align: center;">
                        <a href="{admin_url}" class="button">Ver Detalles y Responder</a>
                    </div>

                    <div class="section">
                        <p style="margin: 0; color: #6c757d; font-size: 14px;">
                            ⏰ Total de mensajes en la conversación: {conv_context.get('total_messages', 0)}
                        </p>
                    </div>
                </div>

                <div class="footer">
                    <p>Este es un mensaje automático del sistema de chat con IA.</p>
                    <p>Por favor, responde al cliente lo antes posible.</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    @staticmethod
    def _build_plain_message(context):
        """Construye el mensaje de texto plano para el email"""
        handoff = context['handoff']
        client_info = context['client_info']
        score = context['score']
        reason = context['reason']
        interests = context['interests']
        conv_context = context['conversation_context']
        admin_url = context['admin_url']

        message = f"""
🚨 NUEVA SOLICITUD DE ATENCIÓN HUMANA

Score del Cliente: {score}/100
Razón: {reason}

--- INFORMACIÓN DEL CLIENTE ---
Nombre: {client_info.get('name', 'No proporcionado')}
Email: {client_info.get('email', 'No proporcionado')}
Teléfono: {client_info.get('phone', 'No proporcionado')}
"""

        if interests.get('services_mentioned'):
            services = ', '.join(interests['services_mentioned'])
            message += f"""
--- SERVICIOS CONSULTADOS ---
{services}
"""

        if conv_context.get('escalation_message'):
            message += f"""
--- ÚLTIMO MENSAJE DEL CLIENTE ---
"{conv_context['escalation_message']}"
"""

        message += f"""
--- DETALLES ---
Total de mensajes en la conversación: {conv_context.get('total_messages', 0)}

Ver detalles completos y responder:
{admin_url}

---
Este es un mensaje automático del sistema de chat con IA.
Por favor, responde al cliente lo antes posible.
"""

        return message

    @staticmethod
    def send_expired_handoff_notification(handoff_request):
        """
        Envía notificación de que un handoff expiró sin respuesta.
        Migrado al sistema centralizado de NotificationService.
        """
        from users.models import CustomUser
        from bot.models import BotConfiguration

        # Obtener configuración del bot para el teléfono del admin
        bot_config = BotConfiguration.objects.filter(is_active=True).first()
        admin_phone = bot_config.admin_phone if bot_config else None

        if not admin_phone:
            logger.warning("No hay teléfono de admin para notificar expiración de handoff %d", handoff_request.id)
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
                role=CustomUser.Role.ADMIN,
                is_active=True
            ).first()

        if not admin_user:
            logger.warning("No se encontró usuario admin para notificar expiración de handoff %d", handoff_request.id)
            return

        client_info = handoff_request.client_contact_info

        # Preparar contexto
        context = {
            "handoff_id": str(handoff_request.id),
            "client_name": client_info.get('name', 'No proporcionado'),
            "created_at": handoff_request.created_at.strftime("%d/%m/%Y %H:%M:%S") if handoff_request.created_at else "Desconocido",
            "admin_url": f"{settings.SITE_URL}/admin/bot/humanhandoffrequest/{handoff_request.id}/change/",
        }

        try:
            NotificationService.send_notification(
                user=admin_user,
                event_code="BOT_HANDOFF_EXPIRED",
                context=context,
                priority="critical"  # Critical para ignorar quiet hours
            )
            logger.info("Notificación de expiración enviada para handoff %d", handoff_request.id)
        except Exception as e:
            logger.error("Error enviando notificación de expiración de handoff %d: %s", handoff_request.id, e)
