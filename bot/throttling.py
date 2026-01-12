from rest_framework.throttling import SimpleRateThrottle


class BotRateThrottle(SimpleRateThrottle):
    """Throttle por minuto para prevenir spam inmediato"""
    scope = 'bot'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user-{request.user.pk}"
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class BotDailyThrottle(SimpleRateThrottle):
    """
    CORRECCIÓN CRÍTICA: Throttle diario para controlar costos de tokens.
    Previene que un usuario consuma más de $0.005 USD/día en tokens de Gemini.
    """
    scope = 'bot_daily'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user-{request.user.pk}"
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class BotIPThrottle(SimpleRateThrottle):
    """
    MEJORA #4: Throttle por IP para prevenir abuso con múltiples cuentas.

    Aplica límite por IP independientemente de autenticación.
    Esto previene que un atacante use múltiples cuentas desde la misma IP.
    """
    scope = 'bot_ip'

    def get_cache_key(self, request, view):
        # Siempre usar IP, incluso si está autenticado
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }
