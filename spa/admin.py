# spa/admin.py

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    ServiceCategory,
    Service,
    StaffAvailability,
    AvailabilityExclusion,
    Appointment,
    AppointmentItem,
    Package,
    Payment,
    # --- INICIO DE LA MODIFICACIÓN: Importar nuevos modelos ---
    PackageService,
    UserPackage,
    Voucher,
    WebhookEvent,
    LoyaltyRewardLog,
    # --- FIN DE LA MODIFICACIÓN ---
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'is_low_supervision')
    search_fields = ('name',)


@admin.register(Service)
class ServiceAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'category', 'duration',
                    'price', 'vip_price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description')
    list_editable = ('price', 'vip_price', 'is_active')


@admin.register(StaffAvailability)
class StaffAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('staff_member', 'get_day_of_week_display',
                    'start_time', 'end_time')
    list_filter = ('staff_member', 'day_of_week')

    def get_day_of_week_display(self, obj):
        return obj.get_day_of_week_display()
    get_day_of_week_display.short_description = 'Day of Week'


@admin.register(AvailabilityExclusion)
class AvailabilityExclusionAdmin(admin.ModelAdmin):
    list_display = (
        'staff_member',
        'date',
        'get_day_of_week_display',
        'start_time',
        'end_time',
        'reason',
    )
    list_filter = ('staff_member', 'day_of_week')
    search_fields = ('staff_member__first_name', 'staff_member__last_name', 'reason')
    autocomplete_fields = ('staff_member',)

    @admin.display(description='Día de la semana')
    def get_day_of_week_display(self, obj):
        return obj.get_day_of_week_display()


class AppointmentItemInline(admin.TabularInline):
    model = AppointmentItem
    extra = 0
    autocomplete_fields = ['service']
    readonly_fields = ('duration', 'price_at_purchase')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'get_services',
        'staff_member',
        'start_time',
        'status',
        'reschedule_count',
    )
    list_filter = ('status', 'staff_member', 'start_time')
    search_fields = (
        'user__phone_number',
        'user__first_name',
        'user__last_name',
        'items__service__name',
    )
    list_select_related = ('user', 'staff_member')
    raw_id_fields = ('user', 'staff_member')
    date_hierarchy = 'start_time'
    inlines = [AppointmentItemInline]

    @admin.display(description='Servicios')
    def get_services(self, obj):
        return obj.get_service_names()


# --- INICIO DE LA MODIFICACIÓN: Usar Inlines para el PackageAdmin ---

class PackageServiceInline(admin.TabularInline):
    """
    Permite editar la cantidad de cada servicio directamente
    en la página de administración del Paquete.
    """
    model = PackageService
    extra = 1  # Muestra 1 campo extra para añadir un nuevo servicio por defecto
    autocomplete_fields = ['service'] # Facilita la búsqueda de servicios

@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active', 'grants_vip_months')
    list_filter = ('is_active',)
    search_fields = ('name',)
    # Se elimina filter_horizontal y se reemplaza con inlines
    inlines = [PackageServiceInline]

# --- FIN DE LA MODIFICACIÓN ---


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction_id', 'user',
                    'appointment', 'amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('transaction_id', 'user__phone_number', 'appointment__id')
    raw_id_fields = ('user', 'appointment')
    list_select_related = ('user', 'appointment')
    date_hierarchy = 'created_at'

# --- INICIO DE LA MODIFICACIÓN: Registrar nuevos modelos ---

@admin.register(UserPackage)
class UserPackageAdmin(admin.ModelAdmin):
    list_display = ('user', 'package', 'purchase_date', 'expires_at')
    search_fields = ('user__first_name', 'user__last_name', 'package__name')
    list_select_related = ('user', 'package', 'payment')
    raw_id_fields = ('user', 'package', 'payment')

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ('code', 'user', 'service', 'status', 'get_expires_at')
    list_filter = ('status', 'service')
    search_fields = ('code', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'service', 'user_package', 'redeemed_appointment')

    @admin.display(description='Expiration Date', ordering='user_package__expires_at')
    def get_expires_at(self, obj):
        return obj.user_package.expires_at

# --- FIN DE LA MODIFICACIÓN ---


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'status', 'created_at')
    search_fields = ('event_type', 'error_message')
    list_filter = ('status', 'event_type')


@admin.register(LoyaltyRewardLog)
class LoyaltyRewardLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'rewarded_at', 'voucher')
    search_fields = ('user__first_name', 'user__last_name')
