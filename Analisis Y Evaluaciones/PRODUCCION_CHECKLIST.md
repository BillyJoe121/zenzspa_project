# Checklist de Preparación para Producción

Aunque la arquitectura de la aplicación es sólida, la configuración actual de despliegue (`Dockerfile`, `docker-compose.yml`) está orientada a desarrollo. Para pasar a producción, debes completar los siguientes pasos críticos:

## 1. Servidor de Aplicaciones (WSGI)
- [ ] **Configurar Gunicorn**: El `Dockerfile` actual usa `runserver` (inseguro para producción).
    - **Cambio requerido**: Modificar `CMD` en `Dockerfile` para usar `gunicorn`.
    - **Ejemplo**: `CMD ["gunicorn", "studiozens.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]`

## 2. Archivos Estáticos (CSS/JS/Images)
- [ ] **Configurar WhiteNoise**: `whitenoise` está instalado pero no configurado en `MIDDLEWARE`.
    - **Acción**: Agregar `whitenoise.middleware.WhiteNoiseMiddleware` en `settings/base.py` (justo después de `SecurityMiddleware`).
    - **Acción**: Configurar `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"`.
    - **Nota**: Sin esto, los estilos CSS no cargarán en producción.

## 3. Seguridad
- [ ] **Variables de Entorno**:
    - Asegurar `DEBUG=False` en el servidor de producción.
    - Generar una `SECRET_KEY` fuerte y única.
    - Configurar `ALLOWED_HOSTS` con el dominio real (ej. `api.studiozens.com`).
- [ ] **HTTPS/SSL**:
    - La aplicación espera que un proxy inverso (Nginx, AWS ALB, Cloudflare) maneje la terminación SSL.
    - Asegurar que `SECURE_SSL_REDIRECT = True` (o manejarlo en el proxy).

## 4. Base de Datos y Caché
- [ ] **PostgreSQL**:
    - No usar la imagen `postgres:alpine` por defecto de docker-compose para datos persistentes críticos sin volúmenes externos gestionados o backups.
    - Se recomienda usar un servicio gestionado (AWS RDS, Google Cloud SQL, Azure Database) para mayor fiabilidad.
- [ ] **Redis**:
    - En producción, usar `rediss://` (con SSL) si el proveedor lo soporta.

## 5. Tareas Asíncronas (Celery)
- [ ] **Worker**: Asegurar que el contenedor de `celery_worker` se despliegue junto con la web.
- [ ] **Beat**: Asegurar que haya **una sola instancia** de `celery_beat` corriendo para evitar duplicidad de tareas programadas.

## 6. Monitoreo
- [ ] **Sentry**: Configurar `SENTRY_DSN` para capturar errores en tiempo real.
- [ ] **Logs**: Configurar un driver de logging en Docker (ej. `json-file` con rotación o envío a CloudWatch/Datadog).
