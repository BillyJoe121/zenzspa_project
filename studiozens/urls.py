# studiozens_project/studiozens/urls.py
from django.contrib import admin
from django.urls import include, path

from .health import health_check_view

api_patterns = [
    path('catalog/', include('spa.urls_catalog')),
    path('marketplace/', include('marketplace.urls')),
    path('', include('spa.urls')),
    path('', include('profiles.urls')),
    path('notifications/', include('notifications.urls')),
    path('', include('core.urls')),
    path('', include('finances.voucher_urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/bot/', include('bot.urls')),
    path('api/v1/analytics/', include('analytics.urls')),
    path('api/v1/finances/', include('finances.urls')),
    path('api/v1/legal/', include('legal.urls')),
    path('api/v1/', include(api_patterns)),
    path('health/', health_check_view, name='health-check'),
    path('metrics/', include('django_prometheus.urls')),
]
