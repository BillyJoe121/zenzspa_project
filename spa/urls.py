# Reemplaza todo el contenido de zenzspa_project/spa/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ServiceCategoryViewSet, ServiceViewSet, PackageViewSet,
    AppointmentViewSet, AvailabilityCheckView, WompiWebhookView,
    InitiatePaymentView, StaffAvailabilityViewSet
)

router = DefaultRouter()
router.register(r'categories', ServiceCategoryViewSet,
                basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'packages', PackageViewSet, basename='package')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'staff-availability', StaffAvailabilityViewSet, basename='staff-availability') # <-- Registrado


# Las URLs de la API para la app 'spa'
urlpatterns = [
    # Rutas gestionadas por el router (CRUD para categorías, servicios, etc.)
    path('', include(router.urls)),

    # Rutas personalizadas para acciones específicas
    path('availability-check/', AvailabilityCheckView.as_view(),
         name='availability-check'),
    path('appointments/<uuid:pk>/initiate-payment/',
         InitiatePaymentView.as_view(), name='initiate-payment'),
    path('payments/wompi-webhook/',
         WompiWebhookView.as_view(), name='wompi-webhook'),
]
