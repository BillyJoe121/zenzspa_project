# --------------------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_prometheus",

    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",                  # CORS
    "csp",                   # Content Security Policy
    "simple_history",
    "django_filters",              # Django Filter para búsquedas avanzadas
    # "axes",                       # Descomenta si usas django-axes para login clásico

    # Tus apps
    "users",
    "spa",
    "profiles",
    "core",
    "marketplace",
    "notifications",
    "analytics",
    "bot",
    "finances",
    "legal",
    "blog",
    "promociones",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # CORS antes de CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "users.middleware.BlockedDeviceMiddleware",  # Bloqueo de dispositivos
    "profiles.middleware.KioskFlowEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "core.infra.middleware.RequestIDMiddleware",
    "core.infra.middleware.AdminAuditMiddleware",
    "core.infra.middleware.PerformanceLoggingMiddleware",  # NUEVO - Logging de performance
    "django_prometheus.middleware.PrometheusAfterMiddleware",
    "legal.middleware.LegalConsentRequiredMiddleware",  # Enforce re-aceptación de términos
    # "axes.middleware.AxesMiddleware",               # Habilita si usas django-axes
]
