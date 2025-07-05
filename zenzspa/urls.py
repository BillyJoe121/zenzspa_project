# zenzspa_project/zenzspa/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Incluye las URLs de la app 'users' bajo el prefijo 'api/v1/auth/'
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/', include('spa.urls')),
    path('api/v1/profiles/', include('profiles.urls')),


]
