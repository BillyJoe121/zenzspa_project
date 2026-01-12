# Lazy imports to avoid circular dependencies during Django startup
default_app_config = "finances.apps.FinancesConfig"
__all__ = [
    "WompiGateway",
    "WompiPaymentClient",
    "build_integrity_signature",
    "WompiDisbursementClient",
    "DeveloperCommissionService",
]


def __getattr__(name):
    if name == "WompiGateway":
        from .gateway import WompiGateway
        return WompiGateway
    elif name == "WompiPaymentClient":
        from .gateway import WompiPaymentClient
        return WompiPaymentClient
    elif name == "build_integrity_signature":
        from .gateway import build_integrity_signature
        return build_integrity_signature
    elif name == "WompiDisbursementClient":
        from .services import WompiDisbursementClient
        return WompiDisbursementClient
    elif name == "DeveloperCommissionService":
        from .services import DeveloperCommissionService
        return DeveloperCommissionService
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
