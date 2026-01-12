from django.contrib import admin

from .models import LegalDocument, UserConsent


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "doc_type", "version", "is_active", "effective_at", "created_at")
    list_filter = ("doc_type", "is_active")
    search_fields = ("title", "slug")
    ordering = ("-created_at",)


@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    list_display = ("document", "document_version", "user", "anonymous_id", "context_type", "context_id", "accepted_at")
    list_filter = ("context_type", "document__doc_type")
    search_fields = ("user__email", "anonymous_id", "context_id", "document__slug")
    ordering = ("-accepted_at",)
