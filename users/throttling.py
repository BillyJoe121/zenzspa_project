from rest_framework.throttling import UserRateThrottle

class AdminRateThrottle(UserRateThrottle):
    scope = 'admin'
