"""
Paquete Gateway de Wompi.

Este paquete fue refactorizado desde un único archivo gateway.py (~856 líneas)
para mejorar la mantenibilidad y organización del código.

Exporta:
- WompiGateway: Cliente para consultar transacciones
- WompiPaymentClient: Cliente para crear transacciones (incluye todos los métodos)
- build_integrity_signature: Generador de firma SHA256
- gateway_latency, gateway_failures: Métricas Prometheus

Módulos internos:
- base: WompiGateway, build_integrity_signature, métricas
- client_base: WompiPaymentClientBase (core)
- pse: PSEMixin (transacciones PSE)
- mobile_wallets: MobileWalletsMixin (Nequi, Daviplata, Bancolombia)
- tokenization: TokenizationMixin (tarjetas, tokens Nequi)
"""
from finances.gateway.base import (
    WompiGateway,
    build_integrity_signature,
    gateway_latency,
    gateway_failures,
)
from finances.gateway.client_base import WompiPaymentClientBase
from finances.gateway.pse import PSEMixin
from finances.gateway.mobile_wallets import MobileWalletsMixin
from finances.gateway.tokenization import TokenizationMixin


class WompiPaymentClient(
    PSEMixin,
    MobileWalletsMixin,
    TokenizationMixin,
    WompiPaymentClientBase
):
    """
    Cliente para crear transacciones en Wompi (cobros).
    
    Combina todos los mixins:
    - PSEMixin: create_pse_transaction, get_pse_financial_institutions
    - MobileWalletsMixin: create_nequi_transaction, create_daviplata_transaction, 
                          create_bancolombia_transfer_transaction
    - TokenizationMixin: tokenize_card, create_payment_source_from_token,
                         tokenize_nequi, get_nequi_token_status
    - WompiPaymentClientBase: create_transaction, resolve_acceptance_token
    """
    pass


__all__ = [
    'WompiGateway',
    'WompiPaymentClient',
    'build_integrity_signature',
    'gateway_latency',
    'gateway_failures',
]
