import os
from urllib.parse import quote_plus

import dj_database_url

from .core import DEBUG

# --------------------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------------------
DATABASES = {}

if os.getenv("DATABASE_URL"):
    # Producción / Render (con URL completa)
    try:
        DATABASES["default"] = dj_database_url.config(
            conn_max_age=60,  # Reducido para mejor compatibilidad con Supabase pooler
            conn_health_checks=True,
            ssl_require=not DEBUG,
        )
        # Añadir opciones de timeout para evitar conexiones colgadas
        DATABASES["default"]["OPTIONS"] = DATABASES["default"].get("OPTIONS", {})
        DATABASES["default"]["OPTIONS"].update({
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",  # 30 segundos max por query
        })
    except Exception as e:
        # Si DATABASE_URL falla, intentar con variables individuales
        print(f"Warning: DATABASE_URL parsing failed: {e}")
        print("Falling back to individual DB environment variables")

        db_password = os.getenv("DB_PASSWORD", "")
        # URL-encode the password if it contains special characters
        encoded_password = quote_plus(db_password) if db_password else ""

        DATABASES["default"] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "studiozens"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": db_password,
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "600")),
            "OPTIONS": {
                "sslmode": os.getenv("DB_SSLMODE", "require"),
                "connect_timeout": 10,
                "client_encoding": "UTF8",
            },
        }
else:
    # Desarrollo local (variables individuales)
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "studiozens"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {
            "sslmode": os.getenv("DB_SSLMODE", "require" if not DEBUG else "disable"),
            "connect_timeout": 10,
            "client_encoding": "UTF8",
        },
    }
