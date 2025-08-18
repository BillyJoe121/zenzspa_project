from django.urls import path, include

urlpatterns = [
    # Ramas principales. Cada app deberá exponer su propio `urls.py`.
    path("auth/", include("authapp.urls")),          # ejemplo
    path("catalog/", include("catalog.urls")),       # ejemplo
    path("booking/", include("booking.urls")),       # ejemplo
    path("me/", include("me.urls")),                 # ejemplo
    path("admin/", include("adminpanel.urls")),      # API administrativa, no Django admin.
]
