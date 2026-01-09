import re


def sanitize_for_logging(text: str, max_length: int = 100) -> str:
    """
    MEJORA #6: Sanitiza texto para logging seguro.

    Remueve caracteres de control que podrían causar log injection
    y trunca el texto para evitar logs excesivamente largos.

    Args:
        text: Texto a sanitizar
        max_length: Longitud máxima del texto (default: 100)

    Returns:
        str: Texto sanitizado y truncado
    """
    if not text:
        return ""

    # Remover caracteres de control (excepto espacios, tabs, newlines normales)
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # Reemplazar saltos de línea y tabs por espacios para logs de una línea
    sanitized = sanitized.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Comprimir múltiples espacios en uno solo
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Truncar si es muy largo
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized.strip()


def anonymize_pii(text: str, max_length: int = 200) -> str:
    """
    Remueve patrones típicos de PII (emails, teléfonos, direcciones) antes de enviarlos al LLM.
    """
    if not text:
        return ""
    # Quitar emails
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "[email]", text)
    # Quitar números con 7+ dígitos (teléfonos)
    text = re.sub(r"\\b\\d{7,15}\\b", "[phone]", text)
    # Quitar direcciones comunes
    text = re.sub(r"(calle|cra|carrera|avenida|av|cll|diag|trans|transversal)\\s+[^\\s,]{1,50}", "[address]", text, flags=re.IGNORECASE)
    return sanitize_for_logging(text, max_length=max_length)
