from pathlib import Path
import os
from typing import Dict

from dotenv import load_dotenv

# Carga de variables de entorno temprana
load_dotenv()


def validate_required_env_vars():
    """
    Valida que todas las variables de entorno críticas estén configuradas.
    """
    required_vars = {
        "SECRET_KEY": "Clave secreta de Django",
    }

    # Validar DB: Si tenemos DATABASE_URL, no exigimos DB_PASSWORD por separado
    if not os.getenv("DATABASE_URL") and not os.getenv("DB_PASSWORD"):
        required_vars["DB_PASSWORD"] = "Contraseña de base de datos (o DATABASE_URL)"

    # En producción, validar más variables
    if os.getenv("DEBUG", "0") not in ("1", "true", "True"):
        required_vars.update({
            "TWILIO_ACCOUNT_SID": "Twilio Account SID",
            "TWILIO_AUTH_TOKEN": "Twilio Auth Token",
            "TWILIO_VERIFY_SERVICE_SID": "Twilio Verify Service SID",
            "WOMPI_PUBLIC_KEY": "Wompi Public Key",
            "WOMPI_PRIVATE_KEY": "Wompi Private Key",
            "WOMPI_INTEGRITY_SECRET": "Wompi Integrity Secret",
            "WOMPI_EVENT_SECRET": "Wompi Event Secret",
            "WOMPI_PAYOUT_PRIVATE_KEY": "Wompi Payout Private Key",
            "WOMPI_PAYOUT_BASE_URL": "Wompi Payout Base URL",
            "WOMPI_DEVELOPER_DESTINATION": "Destino de dispersión para desarrollador",
            "GEMINI_API_KEY": "Gemini API Key para bot",
            "REDIS_URL": "URL de Redis",
            # CELERY_BROKER_URL: Opcional si REDIS_URL está presente (usamos Redis como broker por default)
            "EMAIL_HOST_USER": "Usuario de email",
            "EMAIL_HOST_PASSWORD": "Contraseña de email",
        })

        # Validación lógica condicional para Celery
        if not os.getenv("CELERY_BROKER_URL") and not os.getenv("REDIS_URL"):
            required_vars["CELERY_BROKER_URL"] = "URL del broker de Celery (o REDIS_URL)"

    missing = []
    # Verificar solo las que quedaron en el diccionario
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"{var} ({description})")

    if missing:
        raise RuntimeError(
            "Variables de entorno faltantes:\n"
            + "\n".join(f"  - {var}" for var in missing)
            + "\n\nConfigura estas variables en el archivo .env o como variables de entorno del sistema."
        )


# Validar variables al inicio
validate_required_env_vars()

# --------------------------------------------------------------------------------------
# Paths básicos
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# --------------------------------------------------------------------------------------
# Claves y modo
# --------------------------------------------------------------------------------------
# Admite rotación de llaves secretas (Django 5.2+)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no configurada. Define la variable de entorno antes de iniciar la aplicación.")

# Configuración de encriptación Fernet para datos sensibles (HIPAA/GDPR Compliance)
def _load_fernet_keys():
    """
    Permite rotación: FERNET_KEYS="key_actual,key_anterior" (la primera se usa para cifrar).
    Si no hay lista, usa FERNET_KEY.
    """
    keys: list[bytes] = []
    raw_list = os.getenv("FERNET_KEYS", "")
    for chunk in raw_list.replace(",", " ").split():
        if chunk.strip():
            keys.append(chunk.strip().encode())
    single = os.getenv("FERNET_KEY")
    if single:
        keys.append(single.encode())
    return [k for k in keys if k]


FERNET_KEYS = _load_fernet_keys()
if not FERNET_KEYS:
    if os.getenv("DEBUG", "0") in ("1", "true", "True"):
        from cryptography.fernet import Fernet
        FERNET_KEYS = [Fernet.generate_key()]
        import warnings
        warnings.warn("FERNET_KEY no configurada. Usando clave temporal.", RuntimeWarning)
    else:
        raise RuntimeError("FERNET_KEY no configurada.")
DEBUG = os.getenv("DEBUG", "0") in ("1", "true", "True")


# Helper para listas (definido antes de usarse)
def _split_env(name, default=""):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.replace(",", " ").split() if x.strip()]


# SECRET_KEY_FALLBACKS debe definirse después del helper
SECRET_KEY_FALLBACKS = _split_env("SECRET_KEY_FALLBACKS")


# Hosts/CSRF/CORS: admite coma o espacio
def _parse_action_scores(raw: str) -> Dict[str, float]:
    """
    Convierte una cadena tipo 'otp:0.7,verify:0.3' en un dict.
    Ignora pares malformados para no frenar el arranque.
    """
    mapping: dict[str, float] = {}
    for chunk in raw.split(","):
        if ":" not in chunk:
            continue
        action, score = chunk.split(":", 1)
        try:
            mapping[action.strip()] = float(score.strip())
        except ValueError:
            continue
    return mapping
