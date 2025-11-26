from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

class BurstAnonThrottle(AnonRateThrottle):
    scope = "burst_anon"   # REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['burst_anon'] = '20/min'

class SustainedAnonThrottle(AnonRateThrottle):
    scope = "sustained_anon"  # '200/hour'

class BurstUserThrottle(UserRateThrottle):
    scope = "burst_user"   # '60/min'

class LoginThrottle(AnonRateThrottle):
    scope = "login"        # '5/min'

class AdminThrottle(UserRateThrottle):
    scope = "admin"  # '1000/hour' en settings
    
    def allow_request(self, request, view):
        # Solo aplicar a usuarios admin
        if not request.user or not request.user.is_authenticated:
            return True
        
        if getattr(request.user, 'role', '') != 'ADMIN':
            return True
        
        return super().allow_request(request, view)
