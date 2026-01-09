"""
Core Utils - Validators.
"""
import re
from decimal import Decimal
from datetime import datetime, date
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import serializers


def percentage_0_100(value: int):
    """Valida que un valor esté entre 0 y 100."""
    if value < 0 or value > 100:
        raise serializers.ValidationError("Debe estar entre 0 y 100.")


def validate_colombian_phone(value: str):
    """
    Valida que un número de teléfono sea válido para Colombia.
    Formato: +57XXXXXXXXXX (10 dígitos después del +57)
    """
    pattern = r'^\+57[0-9]{10}$'
    if not re.match(pattern, value):
        raise ValidationError(
            "Número de teléfono inválido. Formato esperado: +57XXXXXXXXXX"
        )


def validate_positive_amount(value: Decimal | float | int):
    """Valida que un monto sea positivo."""
    if value is None:
        return
    
    if value < 0:
        raise ValidationError("El monto debe ser positivo.")
    
    if value == 0:
        raise ValidationError("El monto debe ser mayor que cero.")


def validate_future_date(value: date | datetime):
    """Valida que una fecha sea futura."""
    if not value:
        return
    
    # Convertir a date si es datetime
    if isinstance(value, datetime):
        value = value.date()
    
    today = timezone.now().date()
    if value <= today:
        raise ValidationError("La fecha debe ser futura.")


def validate_date_range(start_date: date | datetime, end_date: date | datetime):
    """
    Valida que un rango de fechas sea válido.
    
    Args:
        start_date: Fecha de inicio
        end_date: Fecha de fin
    
    Raises:
        ValidationError: Si el rango es inválido
    """
    if not start_date or not end_date:
        return
    
    # Convertir a date si son datetime
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    
    if start_date > end_date:
        raise ValidationError("La fecha de inicio debe ser anterior a la fecha de fin.")


def validate_uuid_format(value: str):
    """Valida que un string tenga formato UUID válido."""
    import uuid
    
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValidationError(f"'{value}' no es un UUID válido.")


def validate_min_age(birthdate: date, min_age: int = 18):
    """
    Valida que una persona tenga edad mínima.
    
    Args:
        birthdate: Fecha de nacimiento
        min_age: Edad mínima requerida (default: 18)
    """
    if not birthdate:
        return
    
    today = timezone.now().date()
    age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
    
    if age < min_age:
        raise ValidationError(f"Debe tener al menos {min_age} años.")


def validate_file_size(file, max_size_mb: int = 5):
    """
    Valida el tamaño de un archivo.
    
    Args:
        file: Archivo a validar
        max_size_mb: Tamaño máximo en MB
    """
    if not file:
        return
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file.size > max_size_bytes:
        raise ValidationError(
            f"El archivo es demasiado grande. Tamaño máximo: {max_size_mb}MB"
        )


def validate_image_dimensions(image, max_width: int = 4000, max_height: int = 4000):
    """
    Valida las dimensiones de una imagen.
    
    Args:
        image: Imagen a validar
        max_width: Ancho máximo en píxeles
        max_height: Alto máximo en píxeles
    """
    if not image:
        return
    
    from PIL import Image
    
    try:
        img = Image.open(image)
        width, height = img.size
        
        if width > max_width or height > max_height:
            raise ValidationError(
                f"Dimensiones de imagen demasiado grandes. Máximo: {max_width}x{max_height}px"
            )
    except Exception as e:
        raise ValidationError(f"Error al validar imagen: {str(e)}")
