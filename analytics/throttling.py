from rest_framework.throttling import UserRateThrottle


class AnalyticsRateThrottle(UserRateThrottle):
    """
    Throttle específico para endpoints de analytics.
    Limita requests costosos para prevenir abuso de recursos.
    """
    scope = 'analytics'


class AnalyticsExportRateThrottle(UserRateThrottle):
    """
    Throttle más restrictivo para exportaciones (CSV/XLSX).
    Las exportaciones son operaciones costosas que requieren límites más estrictos.
    """
    scope = 'analytics_export'
