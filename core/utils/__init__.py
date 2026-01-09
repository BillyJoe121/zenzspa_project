"""
Paquete Utils de Core.

Contiene utilidades, validadores, decoradores, excepciones y funciones de caché.

Exporta:
- Helpers: utc_now, to_bogota, get_client_ip, cached_singleton, invalidate, emit_metric, safe_audit_log, retry_with_backoff, batch_process, format_cop, truncate_string
- Validators: percentage_0_100, validate_colombian_phone, validate_positive_amount, validate_future_date, validate_date_range, validate_uuid_format, validate_min_age, validate_file_size, validate_image_dimensions
- Decorators: idempotent_view
- Exceptions: BusinessLogicError, InsufficientFundsError, ResourceConflictError, ServiceUnavailableError, InvalidStateTransitionError, RateLimitExceededError, PermissionDeniedError, drf_exception_handler
- Caching: CacheKeys, GLOBAL_SETTINGS_CACHE_KEY, acquire_lock
"""
from core.utils.helpers import (
    BOGOTA_TZ,
    utc_now,
    to_bogota,
    get_client_ip,
    cached_singleton,
    invalidate,
    emit_metric,
    safe_audit_log,
    retry_with_backoff,
    batch_process,
    format_cop,
    truncate_string,
)
from core.utils.validators import (
    percentage_0_100,
    validate_colombian_phone,
    validate_positive_amount,
    validate_future_date,
    validate_date_range,
    validate_uuid_format,
    validate_min_age,
    validate_file_size,
    validate_image_dimensions,
)
from core.utils.decorators import idempotent_view
from core.utils.exceptions import (
    BusinessLogicError,
    InsufficientFundsError,
    ResourceConflictError,
    ServiceUnavailableError,
    InvalidStateTransitionError,
    RateLimitExceededError,
    PermissionDeniedError,
    drf_exception_handler,
)
from core.utils.caching import CacheKeys, GLOBAL_SETTINGS_CACHE_KEY, acquire_lock


__all__ = [
    # Helpers
    "BOGOTA_TZ",
    "utc_now",
    "to_bogota",
    "get_client_ip",
    "cached_singleton",
    "invalidate",
    "emit_metric",
    "safe_audit_log",
    "retry_with_backoff",
    "batch_process",
    "format_cop",
    "truncate_string",
    # Validators
    "percentage_0_100",
    "validate_colombian_phone",
    "validate_positive_amount",
    "validate_future_date",
    "validate_date_range",
    "validate_uuid_format",
    "validate_min_age",
    "validate_file_size",
    "validate_image_dimensions",
    # Decorators
    "idempotent_view",
    # Exceptions
    "BusinessLogicError",
    "InsufficientFundsError",
    "ResourceConflictError",
    "ServiceUnavailableError",
    "InvalidStateTransitionError",
    "RateLimitExceededError",
    "PermissionDeniedError",
    "drf_exception_handler",
    # Caching
    "CacheKeys",
    "GLOBAL_SETTINGS_CACHE_KEY",
    "acquire_lock",
]
