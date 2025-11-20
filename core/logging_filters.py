"""
Filtros de logging personalizados para el proyecto.

CORRECCIÓN CRÍTICA: Sanitización de información sensible en logs.
"""
import logging
import re


class SanitizeAPIKeyFilter(logging.Filter):
    """
    Filtro de logging que remueve API keys y otra información sensible de los logs.
    
    Este filtro previene la exposición accidental de credenciales en logs de producción,
    especialmente importante cuando se usan servicios de logging externos como Sentry.
    
    Patrones detectados:
    - API keys de Gemini
    - Tokens de autenticación
    - Claves genéricas en formato clave=valor
    - URLs con API keys en query params
    """
    
    # Patrones de regex para detectar información sensible
    PATTERNS = [
        # API keys en formato VARIABLE=valor o VARIABLE: valor
        (
            re.compile(r'(GEMINI_API_KEY["\']?\s*[:=]\s*["\']?)([A-Za-z0-9_-]{20,})'),
            r'\1***REDACTED***'
        ),
        (
            re.compile(r'(TWILIO_AUTH_TOKEN["\']?\s*[:=]\s*["\']?)([A-Za-z0-9_-]{20,})'),
            r'\1***REDACTED***'
        ),
        (
            re.compile(r'(SECRET_KEY["\']?\s*[:=]\s*["\']?)([A-Za-z0-9_-]{20,})'),
            r'\1***REDACTED***'
        ),
        
        # API keys en URLs (query params)
        (
            re.compile(r'([?&]key=)([A-Za-z0-9_-]{20,})'),
            r'\1***REDACTED***'
        ),
        (
            re.compile(r'([?&]api_key=)([A-Za-z0-9_-]{20,})'),
            r'\1***REDACTED***'
        ),
        
        # Tokens de autorización en headers
        (
            re.compile(r'(Authorization:\s*Bearer\s+)([A-Za-z0-9_.-]{20,})'),
            r'\1***REDACTED***'
        ),
        
        # Claves genéricas en formato JSON
        (
            re.compile(r'(["\'](?:api_key|apiKey|token|secret|password)["\']:\s*["\'])([^"\']{8,})(["\'])'),
            r'\1***REDACTED***\3'
        ),
    ]
    
    def filter(self, record):
        """
        Sanitiza el mensaje de log antes de que sea emitido.
        
        Args:
            record: LogRecord a filtrar
            
        Returns:
            bool: Siempre True (no bloqueamos logs, solo los sanitizamos)
        """
        # Sanitizar el mensaje principal
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        
        # Sanitizar argumentos del mensaje
        if record.args:
            if isinstance(record.args, dict):
                # Sanitizar valores del diccionario
                sanitized_args = {}
                for key, value in record.args.items():
                    if isinstance(value, str):
                        for pattern, replacement in self.PATTERNS:
                            value = pattern.sub(replacement, value)
                    sanitized_args[key] = value
                record.args = sanitized_args
            elif isinstance(record.args, (tuple, list)):
                # Sanitizar elementos de la tupla/lista
                sanitized_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        for pattern, replacement in self.PATTERNS:
                            arg = pattern.sub(replacement, arg)
                    sanitized_args.append(arg)
                record.args = tuple(sanitized_args) if isinstance(record.args, tuple) else sanitized_args
        
        return True


class SanitizePIIFilter(logging.Filter):
    """
    Filtro de logging que remueve información personal identificable (PII).
    
    Útil para cumplir con regulaciones de privacidad como GDPR.
    """
    
    PATTERNS = [
        # Números de teléfono (formato internacional)
        (
            re.compile(r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}'),
            '***PHONE***'
        ),
        
        # Emails
        (
            re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            '***EMAIL***'
        ),
        
        # Números de documento (formato colombiano)
        (
            re.compile(r'\b\d{6,10}\b'),  # Cédulas colombianas
            '***ID***'
        ),
    ]
    
    def filter(self, record):
        """Sanitiza PII del mensaje de log."""
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        
        return True
