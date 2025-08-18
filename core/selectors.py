from typing import Iterable
from django.db.models import QuerySet
from .models import AuditLog

def list_audit_logs() -> QuerySet[AuditLog]:
    return AuditLog.objects.select_related("admin_user", "target_user").all()

def list_audit_logs_for_user(user_id) -> Iterable[AuditLog]:
    return AuditLog.objects.filter(target_user_id=user_id).select_related("admin_user", "target_user")
