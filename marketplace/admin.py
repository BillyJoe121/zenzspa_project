from django.contrib import admin

from .models import (
    Product,
    ProductVariant,
    ProductImage,
    Cart,
    CartItem,
    Order,
    OrderItem,
    InventoryMovement,
    ProductReview,
)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('name', 'sku', 'price', 'vip_price', 'stock')
    readonly_fields = ()


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'is_primary', 'alt_text')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'preparation_days')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description')
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'name', 'sku', 'price', 'vip_price', 'stock')
    search_fields = ('name', 'sku', 'product__name')
    list_filter = ('product__category',)
    raw_id_fields = ('product',)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ('variant',)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ('variant',)
    readonly_fields = ('price_at_purchase', 'quantity_returned')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'delivery_option', 'created_at')
    list_filter = ('status', 'delivery_option')
    search_fields = ('user__email', 'tracking_number')
    raw_id_fields = ('user', 'associated_appointment', 'voucher')
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'variant', 'quantity', 'price_at_purchase')
    search_fields = ('order__id', 'variant__sku', 'variant__product__name')
    raw_id_fields = ('order', 'variant')


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ('variant', 'movement_type', 'quantity', 'reference_order', 'created_at')
    list_filter = ('movement_type',)
    search_fields = ('variant__sku', 'reference_order__id')
    raw_id_fields = ('variant', 'reference_order', 'created_by')


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'is_verified_purchase', 'is_approved', 'created_at')
    list_filter = ('rating', 'is_verified_purchase', 'is_approved', 'created_at')
    search_fields = ('product__name', 'user__email', 'title', 'comment')
    raw_id_fields = ('product', 'user', 'order')
    readonly_fields = ('is_verified_purchase', 'created_at', 'updated_at')

    fieldsets = (
        ('Información Básica', {
            'fields': ('product', 'user', 'order', 'rating', 'title', 'comment')
        }),
        ('Estado', {
            'fields': ('is_verified_purchase', 'is_approved', 'admin_response')
        }),
        ('Fechas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
