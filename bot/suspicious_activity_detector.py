"""
Servicio para detectar y registrar actividad sospechosa de usuarios/IPs.
Este servicio se integra con el sistema de seguridad existente para
identificar patrones de abuso y comportamiento malicioso.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import models
from django.db.models import Count, Sum, Q
from .models import (
    SuspiciousActivity, IPBlocklist, BotConversationLog,
    AnonymousUser
)

logger = logging.getLogger(__name__)


class SuspiciousActivityDetector:
    """
    Servicio para detectar y registrar actividades sospechosas.
    """

    @staticmethod
    def check_ip_blocked(ip_address: str) -> tuple[bool, str]:
        """
        Verifica si una IP está bloqueada.

        Returns:
            tuple[bool, str]: (is_blocked, reason)
        """
        block = IPBlocklist.objects.filter(
            ip_address=ip_address,
            is_active=True
        ).first()

        if block and block.is_effective:
            return True, f"Tu IP ha sido bloqueada por: {block.get_reason_display()}. " \
                        f"Contacta al administrador si crees que esto es un error."

        return False, ""

    @staticmethod
    def record_activity(
        user=None,
        anonymous_user=None,
        ip_address=None,
        activity_type=None,
        severity=None,
        description="",
        context=None,
        conversation_log=None
    ):
        """
        Registra una actividad sospechosa en la base de datos.
        Si es crítica, envía alerta por email y verifica auto-bloqueo.

        Args:
            user: Usuario registrado (opcional)
            anonymous_user: Usuario anónimo (opcional)
            ip_address: IP del usuario
            activity_type: Tipo de actividad (SuspiciousActivity.ActivityType)
            severity: Nivel de severidad (SuspiciousActivity.SeverityLevel)
            description: Descripción detallada
            context: Diccionario con contexto adicional
            conversation_log: Log de conversación asociado (opcional)
        """
        try:
            activity = SuspiciousActivity.objects.create(
                user=user,
                anonymous_user=anonymous_user,
                ip_address=ip_address,
                activity_type=activity_type,
                severity=severity,
                description=description,
                context=context or {},
                conversation_log=conversation_log
            )

            logger.warning(
                "Actividad sospechosa registrada: %s - %s - IP: %s - Severidad: %s",
                activity.participant_identifier,
                activity.get_activity_type_display(),
                ip_address,
                activity.get_severity_display()
            )

            # Si es CRÍTICA, enviar alerta y verificar auto-bloqueo
            if severity == SuspiciousActivity.SeverityLevel.CRITICAL:
                # Importar aquí para evitar circular imports
                from .alerts import SuspiciousActivityAlertService, AutoBlockService

                # Enviar alerta por email
                SuspiciousActivityAlertService.send_critical_activity_alert(activity)

                # Verificar si debe bloquearse automáticamente
                was_blocked, block = AutoBlockService.check_and_auto_block(
                    user=user,
                    anonymous_user=anonymous_user,
                    ip_address=ip_address
                )

                if was_blocked:
                    logger.critical(
                        "IP %s auto-bloqueada después de actividad crítica",
                        ip_address
                    )

            return activity

        except Exception as e:
            logger.error("Error registrando actividad sospechosa: %s", e)
            return None

    @classmethod
    def detect_rate_limit_abuse(cls, user, anonymous_user, ip_address):
        """
        Registra cuando un usuario alcanza el límite de velocidad.
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.RATE_LIMIT_HIT,
            severity=SuspiciousActivity.SeverityLevel.MEDIUM,
            description="Usuario alcanzó el límite de velocidad (demasiados mensajes en poco tiempo)",
            context={
                'detection_type': 'velocity_check',
                'timestamp': timezone.now().isoformat()
            }
        )

    @classmethod
    def detect_daily_limit_abuse(cls, user, anonymous_user, ip_address, current_count, limit):
        """
        Registra cuando un usuario alcanza el límite diario.
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.DAILY_LIMIT_HIT,
            severity=SuspiciousActivity.SeverityLevel.HIGH,
            description=f"Usuario alcanzó el límite diario ({current_count}/{limit} mensajes)",
            context={
                'current_count': current_count,
                'limit': limit,
                'timestamp': timezone.now().isoformat()
            }
        )

    @classmethod
    def detect_repetitive_messages(cls, user, anonymous_user, ip_address, message):
        """
        Registra cuando un usuario envía mensajes repetitivos.
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.REPETITIVE_MESSAGES,
            severity=SuspiciousActivity.SeverityLevel.HIGH,
            description="Usuario enviando mensajes muy similares repetidamente",
            context={
                'message_sample': message[:200],  # Primeros 200 caracteres
                'timestamp': timezone.now().isoformat()
            }
        )

    @classmethod
    def detect_jailbreak_attempt(cls, user, anonymous_user, ip_address, message):
        """
        Registra intento de jailbreak o manipulación del prompt.
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.JAILBREAK_ATTEMPT,
            severity=SuspiciousActivity.SeverityLevel.CRITICAL,
            description="Intento de jailbreak o manipulación del prompt del sistema",
            context={
                'message_sample': message[:200],
                'timestamp': timezone.now().isoformat()
            }
        )

    @classmethod
    def detect_malicious_content(cls, user, anonymous_user, ip_address, message, conversation_log=None):
        """
        Registra contenido malicioso detectado por el sistema de seguridad.
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.MALICIOUS_CONTENT,
            severity=SuspiciousActivity.SeverityLevel.CRITICAL,
            description="Contenido malicioso o inapropiado detectado",
            context={
                'message_sample': message[:200],
                'timestamp': timezone.now().isoformat()
            },
            conversation_log=conversation_log
        )

    @classmethod
    def detect_off_topic_spam(cls, user, anonymous_user, ip_address, message, conversation_log=None):
        """
        Registra spam o mensajes fuera de tema repetidos.
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.OFF_TOPIC_SPAM,
            severity=SuspiciousActivity.SeverityLevel.MEDIUM,
            description="Mensajes fuera de tema o spam detectado",
            context={
                'message_sample': message[:200],
                'timestamp': timezone.now().isoformat()
            },
            conversation_log=conversation_log
        )

    @classmethod
    def detect_excessive_tokens(cls, user, anonymous_user, ip_address, tokens_used, conversation_log=None):
        """
        Registra uso excesivo de tokens (mensajes muy largos o complejos).
        """
        return cls.record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=SuspiciousActivity.ActivityType.EXCESSIVE_TOKENS,
            severity=SuspiciousActivity.SeverityLevel.LOW,
            description=f"Uso excesivo de tokens en una conversación ({tokens_used} tokens)",
            context={
                'tokens_used': tokens_used,
                'timestamp': timezone.now().isoformat()
            },
            conversation_log=conversation_log
        )

    @classmethod
    def analyze_user_pattern(cls, user=None, anonymous_user=None, ip_address=None, days=7):
        """
        Analiza patrones de comportamiento de un usuario/IP para detectar anomalías.

        Returns:
            dict: Diccionario con estadísticas y flags de sospecha
        """
        since = timezone.now() - timedelta(days=days)

        # Construir filtro base
        filter_kwargs = {'created_at__gte': since}
        if user:
            filter_kwargs['user'] = user
        elif anonymous_user:
            filter_kwargs['anonymous_user'] = anonymous_user

        # Si tenemos IP, agregar filtro por IP también
        if ip_address:
            filter_kwargs['ip_address'] = ip_address

        # Estadísticas de conversaciones
        conversations = BotConversationLog.objects.filter(**filter_kwargs)

        stats = conversations.aggregate(
            total_messages=Count('id'),
            total_blocked=Count('id', filter=models.Q(was_blocked=True)),
            total_tokens=Sum('tokens_used') or 0
        )

        # Calcular métricas
        avg_messages_per_day = stats['total_messages'] / days if days > 0 else 0
        block_rate = (stats['total_blocked'] / stats['total_messages'] * 100) if stats['total_messages'] > 0 else 0

        # Contar actividades sospechosas registradas
        suspicious_filter = filter_kwargs.copy()
        suspicious_activities = SuspiciousActivity.objects.filter(**suspicious_filter)

        suspicious_count = suspicious_activities.count()
        critical_count = suspicious_activities.filter(
            severity=SuspiciousActivity.SeverityLevel.CRITICAL
        ).count()

        # Determinar flags de sospecha
        is_suspicious = False
        suspicion_reasons = []

        if avg_messages_per_day > 40:
            is_suspicious = True
            suspicion_reasons.append(f"Promedio de {avg_messages_per_day:.1f} mensajes/día (límite: 40)")

        if block_rate > 30:
            is_suspicious = True
            suspicion_reasons.append(f"Tasa de bloqueo del {block_rate:.1f}% (límite: 30%)")

        if suspicious_count > 5:
            is_suspicious = True
            suspicion_reasons.append(f"{suspicious_count} actividades sospechosas registradas")

        if critical_count > 0:
            is_suspicious = True
            suspicion_reasons.append(f"{critical_count} actividades críticas registradas")

        return {
            'period_days': days,
            'total_messages': stats['total_messages'],
            'total_blocked': stats['total_blocked'],
            'total_tokens': stats['total_tokens'],
            'avg_messages_per_day': round(avg_messages_per_day, 1),
            'block_rate': round(block_rate, 1),
            'suspicious_activities': suspicious_count,
            'critical_activities': critical_count,
            'is_suspicious': is_suspicious,
            'suspicion_reasons': suspicion_reasons,
        }


class SuspiciousActivityAnalyzer:
    """
    Analizador para generar reportes y estadísticas de actividades sospechosas.
    Útil para el dashboard del admin.
    """

    @staticmethod
    def get_suspicious_users_summary(days=7, min_severity=SuspiciousActivity.SeverityLevel.MEDIUM):
        """
        Obtiene un resumen de usuarios con actividad sospechosa reciente.

        Args:
            days: Número de días a analizar
            min_severity: Severidad mínima para considerar

        Returns:
            list: Lista de diccionarios con información de usuarios sospechosos
        """
        from django.db.models import Count, Max, Q

        since = timezone.now() - timedelta(days=days)

        # Agrupar por usuario/IP
        activities = SuspiciousActivity.objects.filter(
            created_at__gte=since,
            severity__gte=min_severity
        ).select_related('user', 'anonymous_user')

        # Agrupar por IP
        ip_groups = activities.values('ip_address').annotate(
            total_activities=Count('id'),
            critical_count=Count('id', filter=Q(severity=SuspiciousActivity.SeverityLevel.CRITICAL)),
            high_count=Count('id', filter=Q(severity=SuspiciousActivity.SeverityLevel.HIGH)),
            last_activity=Max('created_at'),
            unreviewed_count=Count('id', filter=Q(reviewed=False))
        ).order_by('-critical_count', '-high_count', '-total_activities')

        results = []
        for ip_data in ip_groups:
            ip_address = ip_data['ip_address']

            # Obtener usuarios asociados a esta IP
            ip_activities = activities.filter(ip_address=ip_address)

            # Usuarios registrados
            users = ip_activities.filter(user__isnull=False).values_list('user_id', flat=True).distinct()
            # Usuarios anónimos
            anon_users = ip_activities.filter(anonymous_user__isnull=False).values_list('anonymous_user_id', flat=True).distinct()

            # Verificar si IP está bloqueada
            is_blocked = IPBlocklist.objects.filter(
                ip_address=ip_address,
                is_active=True
            ).exists()

            # Obtener actividades más recientes
            recent_activities = ip_activities.order_by('-created_at')[:5]

            # Analizar patrón
            pattern = SuspiciousActivityDetector.analyze_user_pattern(
                ip_address=ip_address,
                days=days
            )

            results.append({
                'ip_address': ip_address,
                'is_blocked': is_blocked,
                'total_activities': ip_data['total_activities'],
                'critical_count': ip_data['critical_count'],
                'high_count': ip_data['high_count'],
                'unreviewed_count': ip_data['unreviewed_count'],
                'last_activity': ip_data['last_activity'],
                'registered_users_count': len(users),
                'anonymous_users_count': len(anon_users),
                'pattern_analysis': pattern,
                'recent_activities': [
                    {
                        'id': act.id,
                        'type': act.activity_type,
                        'severity': act.severity,
                        'description': act.description,
                        'created_at': act.created_at,
                        'participant': act.participant_identifier
                    }
                    for act in recent_activities
                ]
            })

        return results

    @staticmethod
    def get_activity_timeline(ip_address=None, user=None, anonymous_user=None, days=30):
        """
        Obtiene la línea de tiempo de actividades de un usuario/IP.

        Returns:
            dict: Timeline con conversaciones y actividades sospechosas
        """
        since = timezone.now() - timedelta(days=days)

        # Filtros
        conv_filter = {'created_at__gte': since}
        susp_filter = {'created_at__gte': since}

        if ip_address:
            conv_filter['ip_address'] = ip_address
            susp_filter['ip_address'] = ip_address
        if user:
            conv_filter['user'] = user
            susp_filter['user'] = user
        if anonymous_user:
            conv_filter['anonymous_user'] = anonymous_user
            susp_filter['anonymous_user'] = anonymous_user

        # Obtener conversaciones
        conversations = BotConversationLog.objects.filter(**conv_filter).order_by('created_at')

        # Obtener actividades sospechosas
        suspicious = SuspiciousActivity.objects.filter(**susp_filter).order_by('created_at')

        # Combinar en timeline
        timeline = []

        for conv in conversations:
            timeline.append({
                'type': 'conversation',
                'timestamp': conv.created_at,
                'message': conv.message[:100],
                'response': conv.response[:100],
                'was_blocked': conv.was_blocked,
                'block_reason': conv.block_reason,
                'tokens_used': conv.tokens_used,
                'id': conv.id
            })

        for susp in suspicious:
            timeline.append({
                'type': 'suspicious_activity',
                'timestamp': susp.created_at,
                'activity_type': susp.activity_type,
                'severity': susp.severity,
                'description': susp.description,
                'reviewed': susp.reviewed,
                'id': susp.id
            })

        # Ordenar por timestamp
        timeline.sort(key=lambda x: x['timestamp'])

        return {
            'period_days': days,
            'total_events': len(timeline),
            'conversations_count': conversations.count(),
            'suspicious_activities_count': suspicious.count(),
            'timeline': timeline
        }
