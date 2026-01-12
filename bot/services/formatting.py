import logging
import re
from decimal import Decimal

from ..security import anonymize_pii

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class _SafeFormatDict(dict):
    def __missing__(self, key):
        logger.warning("Placeholder sin valor para el bot: %s", key)
        return ""


def _format_money(value: Decimal | None) -> str:
    if value is None:
        return "N/D"
    return f"${value:,.0f}".replace(",", ".")


def _clean_text(value: str, max_length: int = 400) -> str:
    """Elimina caracteres de control, anonimiza PII e inyecciones básicas antes de mandar a LLM."""
    return anonymize_pii(value or "", max_length=max_length)


__all__ = [
    "_clean_text",
    "_format_money",
    "_SafeFormatDict",
    "PLACEHOLDER_PATTERN",
]
