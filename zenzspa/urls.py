# zenzspa_project/zenzspa/urls.py
from django.contrib import admin
from django.urls import include, path

api_patterns = [
    path('catalog/', include('spa.urls_catalog')),
    path('', include('marketplace.urls')),
    path('', include('spa.urls')),
    path('', include('profiles.urls')),
    path('notifications/', include('notifications.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/bot/', include('bot.urls')),
    path('api/v1/analytics/', include('analytics.urls')),
    path('api/v1/', include(api_patterns)),
]
