"""
Paquete Infra de Core.

Contiene infraestructura: middleware, logging, métricas.

NOTA: Evitar importar middleware aquí para prevenir ciclos de importación o carga prematura de modelos
durante la configuración de logging en settings.py.
"""
