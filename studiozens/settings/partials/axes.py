import os

# --------------------------------------------------------------------------------------
# Axes (ejemplo de límites si usas login clásico por /admin)
# --------------------------------------------------------------------------------------
AXES_ENABLED = os.getenv("AXES_ENABLED", "0") in ("1", "true", "True")
if AXES_ENABLED:
    AXES_FAILURE_LIMIT = int(
        os.getenv("AXES_FAILURE_LIMIT", "5"))          # 5/min login
    AXES_COOLOFF_TIME = int(
        os.getenv("AXES_COOLOFF_TIME_MIN", "10"))       # 10 minutos
    AXES_ONLY_USER_FAILURES = False
    AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True
