"""
Sistema de notificaciones para escalamiento humano.
Envía notificaciones por email a staff y admin cuando se crea un handoff request.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class HandoffNotificationService:
    """
    Servicio para enviar notificaciones de handoff a staff y admin.
    """

    @staticmethod
    def send_handoff_notification(handoff_request):
        """
        Envía notificación por email a staff y admin sobre un nuevo handoff.

        Args:
            handoff_request: Instancia de HumanHandoffRequest
        """
        from users.models import CustomUser

        # Obtener todos los usuarios staff y admin
        recipients = CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True
        ).values_list('email', flat=True)

        if not recipients:
            logger.warning("No hay recipients para notificación de handoff %d", handoff_request.id)
            return

        # Preparar contexto para el template
        context = {
            'handoff': handoff_request,
            'client_info': handoff_request.client_contact_info,
            'score': handoff_request.client_score,
            'reason': handoff_request.get_escalation_reason_display(),
            'interests': handoff_request.client_interests,
            'conversation_context': handoff_request.conversation_context,
            'admin_url': f"{settings.SITE_URL}/admin/bot/humanhandoffrequest/{handoff_request.id}/change/",
        }

        # Crear subject y body
        subject = f"🚨 Nueva Solicitud de Atención Humana - Score: {handoff_request.client_score}/100"

        # HTML message
        html_message = HandoffNotificationService._build_html_message(context)

        # Plain text fallback
        plain_message = HandoffNotificationService._build_plain_message(context)

        # Enviar email
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(recipients),
                html_message=html_message,
                fail_silently=False,
            )

            logger.info(
                "Notificación de handoff %d enviada a %d destinatarios",
                handoff_request.id, len(recipients)
            )

        except Exception as e:
            logger.error(
                "Error enviando notificación de handoff %d: %s",
                handoff_request.id, e
            )

        # --- WHATSAPP (NUEVO) ---
        from bot.models import BotConfiguration
        bot_config = BotConfiguration.objects.filter(is_active=True).first()
        admin_phone = bot_config.admin_phone if bot_config else None

        if admin_phone and len(admin_phone) > 5:
            # Emoji según score
            score_emoji = "🟢"
            if handoff_request.client_score >= 70:
                score_emoji = "🔴" # Alta prioridad
            elif handoff_request.client_score >= 40:
                score_emoji = "🟡" # Media prioridad

            # Alerta de toxicidad
            sexual_score = handoff_request.conversation_context.get('sexual_score', 0)
            warning_text = ""
            if sexual_score > 0:
                warning_text = "\n⚠️ *ALERTA:* Cliente ha hecho comentarios inapropiados."

            whatsapp_body = f"""🚨 *NUEVA SOLICITUD HUMANA* 🚨
{score_emoji} Score: {handoff_request.client_score}/100
👤 *Cliente:* {handoff_request.client_contact_info.get('name', 'Anónimo')}
📞 *Tel:* {handoff_request.client_contact_info.get('phone', 'N/A')}
{warning_text}

💬 *Dijo:* "{handoff_request.conversation_context.get('escalation_message')}"

_Responde al cliente desde el panel admin._"""

            HandoffNotificationService._send_whatsapp_message(admin_phone, whatsapp_body)

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
        Se envía por Email y WhatsApp al admin.
        """
        from users.models import CustomUser
        from bot.models import BotConfiguration

        # 1. Obtener configuración para el teléfono del admin
        bot_config = BotConfiguration.objects.filter(is_active=True).first()
        admin_phone = bot_config.admin_phone if bot_config else None

        # 2. Obtener admins para email
        recipients = CustomUser.objects.filter(
            role=CustomUser.Role.ADMIN,
            is_active=True
        ).values_list('email', flat=True)

        client_info = handoff_request.client_contact_info
        
        # --- EMAIL ---
        if recipients:
            subject = f"⚠️ ALERTA: Cliente sin atención - Solicitud #{handoff_request.id}"
            
            message = f"""
⚠️ CLIENTE NO ATENDIDO A TIEMPO

El usuario solicitó hablar con un humano y nadie respondió en 5 minutos.
El sistema ha cerrado el chat automáticamente.

--- DATOS DEL CLIENTE ---
Nombre: {client_info.get('name', 'No proporcionado')}
Teléfono: {client_info.get('phone', 'No proporcionado')}
Email: {client_info.get('email', 'No proporcionado')}

--- MENSAJE ORIGINAL ---
"{handoff_request.conversation_context.get('escalation_message', 'No disponible')}"

--- ACCIÓN REQUERIDA ---
Por favor contacta al cliente manualmente lo antes posible.
"""
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=list(recipients),
                    fail_silently=False,
                )
                logger.info("Notificación de expiración enviada por email a %d admins", len(recipients))
            except Exception as e:
                logger.error("Error enviando email de expiración: %s", e)

        # --- WHATSAPP ---
        if admin_phone and len(admin_phone) > 5: # Validación básica
            whatsapp_body = f"""⚠️ *CLIENTE SIN ATENCIÓN* ⚠️
El cliente *{client_info.get('name')}* no recibió respuesta en 5 min.

📞 *Tel:* {client_info.get('phone')}
💬 *Dijo:* "{handoff_request.conversation_context.get('escalation_message')}"

_Por favor contáctalo manualmente._"""
            
            HandoffNotificationService._send_whatsapp_message(admin_phone, whatsapp_body)

    @staticmethod
    def _send_whatsapp_message(to_number, body):
        """Envía mensaje de WhatsApp usando Twilio"""
        try:
            from twilio.rest import Client
            
            account_sid = settings.TWILIO_ACCOUNT_SID
            auth_token = settings.TWILIO_AUTH_TOKEN
            # Número de origen de Twilio (Sandbox o verificado)
            from_number = getattr(settings, 'TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886') 
            
            if not account_sid or not auth_token:
                logger.warning("Twilio no configurado, saltando WhatsApp")
                return

            client = Client(account_sid, auth_token)
            
            # Asegurar formato whatsapp:+numero
            if not to_number.startswith('whatsapp:'):
                to_number = f"whatsapp:{to_number}"
            
            message = client.messages.create(
                from_=from_number,
                body=body,
                to=to_number
            )
            logger.info("WhatsApp enviado a %s: %s", to_number, message.sid)
            
        except Exception as e:
            logger.error("Error enviando WhatsApp: %s", e)
