from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

class BurstAnonThrottle(AnonRateThrottle):
    scope = "burst_anon"   # REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['burst_anon'] = '20/min'

class SustainedAnonThrottle(AnonRateThrottle):
    scope = "sustained_anon"  # '200/hour'

class BurstUserThrottle(UserRateThrottle):
    scope = "burst_user"   # '60/min'

class LoginThrottle(AnonRateThrottle):
    scope = "login"        # '5/min'
