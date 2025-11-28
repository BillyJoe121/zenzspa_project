"""
BOT-PII-PLAIN: Campos cifrados para proteger datos sensibles.

Este módulo proporciona campos de modelo que automáticamente cifran/descifran
datos usando las claves FERNET configuradas en settings.

Uso:
    from bot.encrypted_fields import EncryptedTextField
    
    class MyModel(models.Model):
        sensitive_data = EncryptedTextField()
"""

from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


class EncryptedTextField(models.TextField):
    """
    Campo de texto que automáticamente cifra/descifra datos usando Fernet.
    
    Los datos se almacenan cifrados en la base de datos y se descifran
    automáticamente al leer.
    """
    
    description = "Encrypted text field using Fernet"
    
    def __init__(self, *args, **kwargs):
        # Permitir null para compatibilidad
        kwargs.setdefault('null', True)
        kwargs.setdefault('blank', True)
        super().__init__(*args, **kwargs)
    
    def get_fernet(self):
        """Obtiene una instancia de Fernet con la clave configurada"""
        fernet_keys = getattr(settings, 'FERNET_KEYS', [])
        if not fernet_keys or not fernet_keys[0]:
            raise ValueError(
                "FERNET_KEYS no configurada. Define FERNET_KEY en variables de entorno."
            )
        return Fernet(fernet_keys[0])
    
    def get_prep_value(self, value):
        """Cifra el valor antes de guardarlo en la base de datos"""
        if value is None or value == '':
            return None
        
        try:
            fernet = self.get_fernet()
            # Convertir a bytes si es string
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
            else:
                value_bytes = value
            
            # Cifrar y convertir a string para almacenar
            encrypted = fernet.encrypt(value_bytes)
            return encrypted.decode('utf-8')
        except Exception as e:
            logger.error("Error cifrando datos: %s", e)
            # En caso de error, no guardar el valor
            raise ValueError(f"Error cifrando datos: {e}")
    
    def from_db_value(self, value, expression, connection):
        """Descifra el valor al leerlo de la base de datos"""
        if value is None or value == '':
            return None
        
        try:
            fernet = self.get_fernet()
            # Convertir a bytes si es string
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
            else:
                value_bytes = value
            
            # Descifrar
            decrypted = fernet.decrypt(value_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error("Error descifrando datos: %s", e)
            # Retornar None si no se puede descifrar
            return None
    
    def to_python(self, value):
        """Convierte el valor a Python (usado en formularios)"""
        if value is None or value == '':
            return None
        
        # Si ya está descifrado (string normal), retornarlo
        if isinstance(value, str) and not value.startswith('gAAAAA'):
            return value
        
        # Si está cifrado, descifrarlo
        return self.from_db_value(value, None, None)


class EncryptedJSONField(models.JSONField):
    """
    Campo JSON que automáticamente cifra/descifra datos usando Fernet.
    
    Los datos se almacenan cifrados en la base de datos como texto
    y se descifran automáticamente al leer.
    """
    
    description = "Encrypted JSON field using Fernet"
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('null', True)
        kwargs.setdefault('blank', True)
        super().__init__(*args, **kwargs)
    
    def get_fernet(self):
        """Obtiene una instancia de Fernet con la clave configurada"""
        fernet_keys = getattr(settings, 'FERNET_KEYS', [])
        if not fernet_keys or not fernet_keys[0]:
            raise ValueError(
                "FERNET_KEYS no configurada. Define FERNET_KEY en variables de entorno."
            )
        return Fernet(fernet_keys[0])
    
    def get_prep_value(self, value):
        """Cifra el valor JSON antes de guardarlo"""
        if value is None:
            return None
        
        try:
            import json
            fernet = self.get_fernet()
            
            # Convertir a JSON string
            json_str = json.dumps(value, ensure_ascii=False)
            json_bytes = json_str.encode('utf-8')
            
            # Cifrar
            encrypted = fernet.encrypt(json_bytes)
            return encrypted.decode('utf-8')
        except Exception as e:
            logger.error("Error cifrando JSON: %s", e)
            raise ValueError(f"Error cifrando JSON: {e}")
    
    def from_db_value(self, value, expression, connection):
        """Descifra el valor JSON al leerlo de la base de datos"""
        if value is None:
            return None
        
        try:
            import json
            fernet = self.get_fernet()
            
            # Convertir a bytes si es string
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
            else:
                value_bytes = value
            
            # Descifrar
            decrypted = fernet.decrypt(value_bytes)
            json_str = decrypted.decode('utf-8')
            
            # Parsear JSON
            return json.loads(json_str)
        except Exception as e:
            logger.error("Error descifrando JSON: %s", e)
            return None
    
    def to_python(self, value):
        """Convierte el valor a Python"""
        if value is None:
            return None
        
        # Si ya es un dict/list, retornarlo
        if isinstance(value, (dict, list)):
            return value
        
        # Si está cifrado, descifrarlo
        return self.from_db_value(value, None, None)


def sanitize_pii(text):
    """
    Sanitiza PII (Personally Identifiable Information) de un texto.
    
    Reemplaza:
    - Emails con [EMAIL]
    - Teléfonos con [PHONE]
    - Números de documento con [ID]
    
    Args:
        text: Texto a sanitizar
        
    Returns:
        Texto sanitizado
    """
    import re
    
    if not text:
        return text
    
    # Reemplazar emails
    text = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '[EMAIL]',
        text
    )
    
    # Reemplazar teléfonos (formatos comunes)
    # +57 300 123 4567, 300-123-4567, 3157589548, etc.
    text = re.sub(
        r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        '[PHONE]',
        text
    )
    
    # Reemplazar números de documento (cédulas, pasaportes)
    # Números de 6-12 dígitos
    text = re.sub(
        r'\b\d{6,12}\b',
        '[ID]',
        text
    )
    
    return text
