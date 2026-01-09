from .core import DEBUG
from .rest_framework import REST_FRAMEWORK

# --------------------------------------------------------------------------------------
# DRF Browsable API solo en debug
# --------------------------------------------------------------------------------------
if DEBUG:
    REST_FRAMEWORK.setdefault(
        "DEFAULT_RENDERER_CLASSES",
        (
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ),
    )
else:
    REST_FRAMEWORK.setdefault(
        "DEFAULT_RENDERER_CLASSES",
        ("rest_framework.renderers.JSONRenderer",),
    )
