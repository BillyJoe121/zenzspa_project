from pathlib import Path
import os
from dotenv import load_dotenv  # <--- IMPORT
from datetime import timedelta
from celery.schedules import crontab


load_dotenv()  # <--- LLAMADA A LA FUNCIÓN

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')

# DEBUG = os.getenv('DEBUG') == '1'

DEBUG = True

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Aplicaciones de terceros
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',


    # Mis aplicaciones
    'users',
    'spa',
    'profiles',
    'core',


]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'zenzspa.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'zenzspa.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

# Modelo de Usuario Personalizado
AUTH_USER_MODEL = 'users.CustomUser'

# Configuración de Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    )
}

# Configuración de Simple JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": "",
    "AUDIENCE": None,
    "ISSUER": None,
    "JSON_ENCODER": None,
    "JWK_URL": None,
    "LEEWAY": 0,

    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "phone_number",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",

    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",

    "JTI_CLAIM": "jti",
}

# Configuración de Caché con Redis
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "TIMEOUT": 300,  # 5 minutos
    }
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_VERIFY_SERVICE_SID = os.getenv('TWILIO_VERIFY_SERVICE_SID')


# --- Wompi Configuration (Sandbox Test Keys) ---
# Llaves obtenidas de la documentación de Wompi para el ambiente de Sandbox
WOMPI_PUBLIC_KEY = 'pub_test_QzG324W7146F543D56f4B4A93425b294'
# El secreto de integridad es para generar la firma que se envía al widget.
WOMPI_INTEGRITY_SECRET = 'test_integrity_477346_f4d6CB422789E62b16895c1a79D81b69'
# El secreto de eventos es para verificar la autenticidad de los webhooks que recibimos.
WOMPI_EVENT_SECRET = 'test_events_7761_d8A97259400263f45EAb29A6b283942C'

# La URL de redirección después del pago (puede ser una página de "gracias" en el frontend)
# Ajustar si tu frontend corre en otro puerto
WOMPI_REDIRECT_URL = 'http://localhost:3000/payment-result'


# --- Celery Configuration ---
# Usamos la base de datos 0 de Redis para Celery, y la 1 para la caché, para mantenerlos separados.
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE  # Usamos la misma zona horaria que Django

# --- Celery Beat Settings ---
CELERY_BEAT_SCHEDULE = {
    'check-for-reminders-every-hour': {
        'task': 'spa.tasks.check_and_queue_reminders',
        # Se corrige para que se ejecute cada hora, en el minuto 0.
        'schedule': crontab(minute='0', hour='*'),
    },
    'cancel-unpaid-appointments-every-10-minutes': {
        'task': 'spa.tasks.cancel_unpaid_appointments',
        # Se ejecuta cada 10 minutos para asegurar que las citas se cancelen a tiempo.
        'schedule': crontab(minute='*/10'),
    },
}


# --- Email Configuration (Development) ---
# En lugar de un servidor SMTP, usamos el backend de consola.
# Imprimirá los correos en la terminal donde se ejecuta runserver.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Dirección de correo por defecto para enviar correos (ej. no-reply@zenzspa.com)
DEFAULT_FROM_EMAIL = 'ZenzSpa <no-reply@zenzspa.com>'
