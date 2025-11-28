"""
Admin interface para el módulo finances.
"""
from django.contrib import admin
from .models import (
    Payment,
    PaymentCreditUsage,
    ClientCredit,
    FinancialAdjustment,
    SubscriptionLog,
    WebhookEvent,
    CommissionLedger,
)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'status', 'payment_type', 'transaction_id', 'created_at')
    list_filter = ('status', 'payment_type', 'created_at')
    search_fields = ('transaction_id', 'user__email', 'user__phone_number')
    readonly_fields = ('created_at', 'updated_at', 'raw_response')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Información Básica', {
            'fields': ('user', 'amount', 'status', 'payment_type', 'transaction_id')
        }),
        ('Referencias', {
            'fields': ('appointment', 'order', 'used_credit')
        }),
        ('Datos del Cliente (Wompi)', {
            'fields': ('customer_legal_id', 'customer_legal_id_type'),
            'classes': ('collapse',)
        }),
        ('Método de Pago', {
            'fields': ('payment_method_type', 'payment_method_data'),
            'classes': ('collapse',)
        }),
        ('Información Fiscal', {
            'fields': ('tax_vat_in_cents', 'tax_consumption_in_cents'),
            'classes': ('collapse',)
        }),
        ('Detalles Técnicos', {
            'fields': ('raw_response', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ClientCredit)
class ClientCreditAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'initial_amount', 'remaining_amount', 'status', 'expires_at', 'created_at')
    list_filter = ('status', 'created_at', 'expires_at')
    search_fields = ('user__email', 'user__phone_number')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(FinancialAdjustment)
class FinancialAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'adjustment_type', 'created_by', 'created_at')
    list_filter = ('adjustment_type', 'created_at')
    search_fields = ('user__email', 'user__phone_number', 'reason')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(SubscriptionLog)
class SubscriptionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'start_date', 'end_date', 'payment', 'created_at')
    list_filter = ('start_date', 'end_date', 'created_at')
    search_fields = ('user__email', 'user__phone_number')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'start_date'


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'status', 'created_at')
    list_filter = ('status', 'event_type', 'created_at')
    search_fields = ('event_type', 'error_message')
    readonly_fields = ('created_at', 'updated_at', 'payload', 'headers')
    date_hierarchy = 'created_at'


@admin.register(CommissionLedger)
class CommissionLedgerAdmin(admin.ModelAdmin):
    list_display = ('id', 'amount', 'paid_amount', 'pending_amount', 'status', 'source_payment', 'created_at')
    list_filter = ('status', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'pending_amount')
    date_hierarchy = 'created_at'


@admin.register(PaymentCreditUsage)
class PaymentCreditUsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'credit', 'amount', 'created_at')
    list_filter = ('created_at',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
