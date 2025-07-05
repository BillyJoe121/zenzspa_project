from django.contrib import admin
from .models import (
    ServiceCategory,
    Service,
    StaffAvailability,
    Appointment,
    Package,
    Payment
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_low_supervision')
    search_fields = ('name',)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
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


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'service', 'staff_member',
                    'start_time', 'status', 'reschedule_count')
    list_filter = ('status', 'staff_member', 'service', 'start_time')
    search_fields = ('user__phone_number', 'user__first_name',
                     'user__last_name', 'service__name')
    list_select_related = ('user', 'service', 'staff_member')
    raw_id_fields = ('user', 'staff_member', 'service')
    date_hierarchy = 'start_time'


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active', 'grants_vip_months')
    list_filter = ('is_active',)
    search_fields = ('name',)
    filter_horizontal = ('services',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction_id', 'user',
                    'appointment', 'amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('transaction_id', 'user__phone_number', 'appointment__id')
    raw_id_fields = ('user', 'appointment')
    list_select_related = ('user', 'appointment')
    date_hierarchy = 'created_at'
