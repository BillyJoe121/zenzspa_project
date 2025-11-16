from rest_framework.throttling import SimpleRateThrottle


class BotRateThrottle(SimpleRateThrottle):
    scope = 'bot'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user-{request.user.pk}"
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
