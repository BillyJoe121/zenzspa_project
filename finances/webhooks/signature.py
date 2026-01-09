import hashlib

from django.conf import settings
from django.utils import timezone

from .shared import logger, webhook_signature_errors


def validate_signature(request_body, data, event_type, timestamp):
    """
    Valida la firma del evento según el algoritmo oficial de Wompi.

    Algoritmo oficial:
    1. Extraer properties del signature object
    2. Obtener valores de data según properties
    3. Concatenar valores + timestamp + secret
    4. SHA256 y comparar con checksum

    Referencia: https://docs.wompi.co/docs/es/eventos#seguridad
    """
    if not all([data, timestamp]):
        logger.error(
            "[PAYMENT-ALERT] Webhook Error: Datos incompletos (event=%s)", event_type
        )
        raise ValueError("Datos del webhook incompletos.")

    signature_obj = request_body.get("signature", {})
    properties = signature_obj.get("properties", [])
    sent_checksum = signature_obj.get("checksum")

    if not sent_checksum or not properties:
        logger.error(
            "[PAYMENT-ALERT] Webhook Error: Firma o properties ausentes (event=%s)", event_type
        )
        webhook_signature_errors.labels(event_type or "unknown").inc()
        raise ValueError("Firma del webhook incompleta.")

    # Validar frescura del timestamp para prevenir replays
    try:
        event_ts = int(timestamp)
    except (TypeError, ValueError):
        logger.error("[PAYMENT-ALERT] Webhook Error: Timestamp inválido (event=%s)", event_type)
        raise ValueError("Timestamp inválido en webhook.")

    now_ts = int(timezone.now().timestamp())
    if abs(now_ts - event_ts) > 300:
        logger.error(
            "[PAYMENT-ALERT] Webhook Error: Timestamp fuera de ventana (event=%s, ts=%s, now=%s)",
            event_type,
            timestamp,
            now_ts,
        )
        raise ValueError("Webhook demasiado antiguo o en el futuro.")

    # Paso 1: Concatenar valores según properties del evento
    values = []
    for prop_path in properties:
        keys = prop_path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, "")
            else:
                value = ""
                break

        values.append(str(value))

    concatenated = "".join(values)

    # Paso 2: Agregar timestamp
    concatenated += str(timestamp)

    # Paso 3: Agregar secreto de eventos
    event_secret = getattr(settings, "WOMPI_EVENT_SECRET", "")
    if not event_secret:
        logger.error("[PAYMENT-ALERT] WOMPI_EVENT_SECRET no configurado")
        raise ValueError("WOMPI_EVENT_SECRET no está configurado.")

    concatenated += event_secret

    # Paso 4: Calcular SHA256
    calculated_checksum = hashlib.sha256(concatenated.encode('utf-8')).hexdigest()

    # Paso 5: Comparar checksums (case-insensitive)
    if calculated_checksum.upper() != sent_checksum.upper():
        logger.error(
            "[PAYMENT-ALERT] Webhook Error: Firma inválida (event=%s). "
            "Calculado: %s, Recibido: %s, Properties: %s",
            event_type,
            calculated_checksum,
            sent_checksum,
            properties
        )
        webhook_signature_errors.labels(event_type or "unknown").inc()
        raise ValueError("Firma del webhook inválida. La petición podría ser fraudulenta.")

    logger.info("[PAYMENT-SUCCESS] Webhook validado correctamente (event=%s)", event_type)
