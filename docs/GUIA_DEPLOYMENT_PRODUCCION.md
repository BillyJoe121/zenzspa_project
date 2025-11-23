# 🚀 GUÍA COMPLETA DE DEPLOYMENT A PRODUCCIÓN - ZENZSPA

**Fecha**: 2025-11-23  
**Autor**: Guía para primer deployment en Render  
**Objetivo**: Desplegar zenzspa_project a producción de forma segura

---

## 📋 TABLA DE CONTENIDOS

1. [Pre-requisitos](#pre-requisitos)
2. [Fase 1: Preparación Local](#fase-1-preparación-local)
3. [Fase 2: Configuración de Servicios Externos](#fase-2-configuración-de-servicios-externos)
4. [Fase 3: Configuración de Render](#fase-3-configuración-de-render)
5. [Fase 4: Deployment](#fase-4-deployment)
6. [Fase 5: Post-Deployment](#fase-5-post-deployment)
7. [Fase 6: Monitoreo y Mantenimiento](#fase-6-monitoreo-y-mantenimiento)
8. [Troubleshooting](#troubleshooting)

---

## PRE-REQUISITOS

### ✅ Lo que ya tienes:
- [x] API Key de Gemini
- [x] Llaves de Wompi del negocio
- [x] Presupuesto para Render

### ✅ Lo que necesitas preparar:
- [ ] Cuenta en Render.com
- [ ] Cuenta en Sentry.io (monitoreo de errores - GRATIS)
- [ ] Cuenta en SendGrid o similar (emails - GRATIS hasta 100/día)
- [ ] Dominio personalizado (opcional pero recomendado)
- [ ] Cuenta de GitHub (para CI/CD)

---

## FASE 1: PREPARACIÓN LOCAL

### **Paso 1.1: Implementar Mejoras Críticas** ⏱️ 2-4 semanas

Antes de desplegar, implementa **mínimo las top 20 críticas**:

```bash
# Crear rama para mejoras
git checkout -b feature/production-improvements

# Implementar en orden:
# 1. Zenzspa: Validación de env vars
# 2. Zenzspa: Rate limiting
# 3. Core: Race conditions
# 4. Spa: Race conditions + Circuit breaker
# 5. Users: Rate limiting OTP + Circuit breaker
# 6. Profiles: Encriptación + Auditoría
# 7. Finances: Circuit breaker + Auditoría
# 8. Cleanup tasks (IdempotencyKey, NotificationLog, etc.)
```

### **Paso 1.2: Tests Completos** ⏱️ 1-2 semanas

#### A. Tests Unitarios (mínimo 60% cobertura)

```bash
# Instalar coverage
pip install coverage pytest-cov

# Ejecutar tests con cobertura
pytest --cov=. --cov-report=html --cov-report=term

# Ver reporte
open htmlcov/index.html  # En Windows: start htmlcov/index.html
```

**Mínimo requerido por módulo**:
- ✅ Core: Tests de GlobalSettings, IdempotencyKey, decorators
- ✅ Users: Tests de autenticación, OTP, permisos
- ✅ Spa: Tests de disponibilidad, appointments, pagos
- ✅ Profiles: Tests de anonimización, permisos, kiosk
- ✅ Finances: Tests de comisiones, cálculos
- ✅ Notifications: Tests de envío, templates
- ✅ Analytics: Tests de KPIs, cálculos

#### B. Tests de Integración

```python
# Crear tests/integration/test_appointment_flow.py
def test_complete_appointment_flow():
    """Test del flujo completo: crear cita → pagar → confirmar"""
    # 1. Usuario se registra
    # 2. Verifica OTP
    # 3. Crea cita
    # 4. Paga con Wompi (mock)
    # 5. Cita se confirma
    # 6. Comisión se registra
    pass

def test_cancellation_flow_with_strikes():
    """Test del flujo de cancelación con sistema de strikes"""
    pass

def test_kiosk_session_flow():
    """Test del flujo completo de kiosk"""
    pass
```

#### C. Colección de Postman

```bash
# Exportar colección de Postman con:
# 1. Autenticación (registro, login, OTP)
# 2. Perfiles (CRUD, anonimización)
# 3. Citas (crear, reagendar, cancelar)
# 4. Pagos (crear, webhook Wompi)
# 5. Bot (mensajes)
# 6. Analytics (KPIs, reportes)
# 7. Kiosk (sesiones)

# Incluir:
# - Variables de entorno ({{base_url}}, {{token}})
# - Tests automáticos en cada request
# - Flujos completos (collections runs)
```

### **Paso 1.3: Preparar Archivos de Deployment**

#### A. Crear `requirements-prod.txt`

```txt
# requirements-prod.txt
# Producción: versiones fijas para estabilidad

# Django y DRF
Django==4.2.7
djangorestframework==3.14.0
djangorestframework-simplejwt==5.3.0

# Base de datos
psycopg2-binary==2.9.9
dj-database-url==2.1.0

# Cache y Celery
redis==5.0.1
django-redis==5.4.0
celery==5.3.4

# Seguridad
django-cors-headers==4.3.1
django-csp==3.8

# Integraciones
twilio==8.10.0
google-generativeai==0.3.1
requests==2.31.0

# Utilidades
python-dotenv==1.0.0
Pillow==10.1.0
openpyxl==3.1.2
phonenumbers==8.13.26

# Monitoreo
sentry-sdk==1.38.0

# WSGI
gunicorn==21.2.0
whitenoise==6.6.0

# Historial
django-simple-history==3.4.0

# IMPORTANTE: Fijar versiones para evitar breaking changes
```

#### B. Crear `Dockerfile` (opcional pero recomendado)

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements-prod.txt .

# Instalar dependencias Python
RUN pip install --upgrade pip && \
    pip install -r requirements-prod.txt

# Copiar código
COPY . .

# Crear directorio para logs
RUN mkdir -p logs

# Recolectar archivos estáticos
RUN python manage.py collectstatic --noinput

# Exponer puerto
EXPOSE 8000

# Comando de inicio
CMD ["gunicorn", "zenzspa.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

#### C. Crear `render.yaml` (Blueprint de Render)

```yaml
# render.yaml
services:
  # Web Service (Django)
  - type: web
    name: zenzspa-web
    env: python
    region: oregon
    plan: starter  # $7/mes
    buildCommand: "./build.sh"
    startCommand: "gunicorn zenzspa.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --timeout 120"
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: DATABASE_URL
        fromDatabase:
          name: zenzspa-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: zenzspa-redis
          property: connectionString
      - key: SECRET_KEY
        generateValue: true
      - key: DEBUG
        value: "0"
      - key: ALLOWED_HOSTS
        sync: false  # Configurar manualmente
      - key: GEMINI_API_KEY
        sync: false  # Configurar manualmente
      - key: TWILIO_ACCOUNT_SID
        sync: false
      - key: TWILIO_AUTH_TOKEN
        sync: false
      - key: WOMPI_PUBLIC_KEY
        sync: false
      - key: WOMPI_INTEGRITY_SECRET
        sync: false
      - key: SENTRY_DSN
        sync: false

  # Worker (Celery)
  - type: worker
    name: zenzspa-worker
    env: python
    region: oregon
    plan: starter
    buildCommand: "./build.sh"
    startCommand: "celery -A zenzspa worker -l info"
    envVars:
      - fromService:
          type: web
          name: zenzspa-web
          envVarKey: DATABASE_URL
      - fromService:
          type: web
          name: zenzspa-web
          envVarKey: REDIS_URL

  # Celery Beat (Tareas programadas)
  - type: worker
    name: zenzspa-beat
    env: python
    region: oregon
    plan: starter
    buildCommand: "./build.sh"
    startCommand: "celery -A zenzspa beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler"
    envVars:
      - fromService:
          type: web
          name: zenzspa-web
          envVarKey: DATABASE_URL

databases:
  # PostgreSQL
  - name: zenzspa-db
    databaseName: zenzspa
    user: zenzspa
    region: oregon
    plan: starter  # $7/mes

  # Redis
  - name: zenzspa-redis
    region: oregon
    plan: starter  # $7/mes
    maxmemoryPolicy: allkeys-lru
```

#### D. Crear `build.sh`

```bash
#!/usr/bin/env bash
# build.sh - Script de build para Render

set -o errexit  # Exit on error

echo "📦 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements-prod.txt

echo "🗄️ Ejecutando migraciones..."
python manage.py migrate --noinput

echo "📊 Creando superusuario si no existe..."
python manage.py shell << EOF
from users.models import CustomUser
if not CustomUser.objects.filter(phone_number='+573000000000').exists():
    CustomUser.objects.create_superuser(
        phone_number='+573000000000',
        email='admin@zenzspa.com',
        first_name='Admin',
        password='CHANGE_THIS_PASSWORD'
    )
EOF

echo "📁 Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

echo "✅ Build completado!"
```

```bash
# Hacer ejecutable
chmod +x build.sh
```

---

## FASE 2: CONFIGURACIÓN DE SERVICIOS EXTERNOS

### **Paso 2.1: Sentry (Monitoreo de Errores)** ⏱️ 30 min

1. **Crear cuenta en Sentry.io** (GRATIS)
   - Ir a https://sentry.io/signup/
   - Crear organización "ZenzSpa"
   - Crear proyecto "zenzspa-backend" (Django)

2. **Obtener DSN**
   ```
   Settings → Projects → zenzspa-backend → Client Keys (DSN)
   
   Ejemplo: https://abc123@o123456.ingest.sentry.io/123456
   ```

3. **Configurar en .env**
   ```bash
   SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/123456
   SENTRY_ENV=production
   SENTRY_TRACES_SAMPLE_RATE=0.1
   ```

### **Paso 2.2: SendGrid (Emails)** ⏱️ 30 min

1. **Crear cuenta en SendGrid** (GRATIS hasta 100 emails/día)
   - Ir a https://signup.sendgrid.com/
   - Verificar email

2. **Crear API Key**
   ```
   Settings → API Keys → Create API Key
   Nombre: zenzspa-production
   Permisos: Full Access (o Mail Send)
   ```

3. **Verificar dominio** (opcional pero recomendado)
   ```
   Settings → Sender Authentication → Domain Authentication
   Agregar registros DNS de tu dominio
   ```

4. **Configurar en .env**
   ```bash
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.sendgrid.net
   EMAIL_PORT=587
   EMAIL_USE_TLS=1
   EMAIL_HOST_USER=apikey
   EMAIL_HOST_PASSWORD=SG.tu_api_key_aqui
   DEFAULT_FROM_EMAIL=ZenzSpa <no-reply@tudominio.com>
   ```

### **Paso 2.3: Twilio (Ya lo tienes configurado)** ✅

Verificar que tengas:
```bash
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_VERIFY_SERVICE_SID=VA...
```

### **Paso 2.4: Wompi (Ya lo tienes configurado)** ✅

Verificar que tengas las llaves de **PRODUCCIÓN**:
```bash
WOMPI_PUBLIC_KEY=pub_prod_...
WOMPI_INTEGRITY_SECRET=prod_integrity_...
WOMPI_EVENT_SECRET=prod_events_...
WOMPI_REDIRECT_URL=https://tudominio.com/payment-result
```

⚠️ **IMPORTANTE**: Asegúrate de usar llaves de PRODUCCIÓN, no de pruebas.

### **Paso 2.5: Gemini (Ya lo tienes configurado)** ✅

```bash
GEMINI_API_KEY=tu_api_key_aqui
GEMINI_MODEL=gemini-1.5-flash
BOT_GEMINI_TIMEOUT=20
```

---

## FASE 3: CONFIGURACIÓN DE RENDER

### **Paso 3.1: Crear Cuenta en Render** ⏱️ 15 min

1. Ir a https://render.com/
2. Registrarse con GitHub
3. Conectar repositorio de zenzspa_project

### **Paso 3.2: Crear PostgreSQL Database** ⏱️ 10 min

1. Dashboard → New → PostgreSQL
2. Configuración:
   ```
   Name: zenzspa-db
   Database: zenzspa
   User: zenzspa
   Region: Oregon (o el más cercano)
   Plan: Starter ($7/mes)
   ```
3. **Guardar Internal Database URL** (la necesitarás)

### **Paso 3.3: Crear Redis Instance** ⏱️ 10 min

1. Dashboard → New → Redis
2. Configuración:
   ```
   Name: zenzspa-redis
   Region: Oregon
   Plan: Starter ($7/mes)
   Maxmemory Policy: allkeys-lru
   ```
3. **Guardar Internal Redis URL**

### **Paso 3.4: Crear Web Service (Django)** ⏱️ 30 min

1. Dashboard → New → Web Service
2. Conectar repositorio GitHub
3. Configuración:
   ```
   Name: zenzspa-web
   Region: Oregon
   Branch: main
   Root Directory: (dejar vacío)
   Runtime: Python 3
   Build Command: ./build.sh
   Start Command: gunicorn zenzspa.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --timeout 120
   Plan: Starter ($7/mes)
   ```

4. **Environment Variables** (⚠️ CRÍTICO):
   ```bash
   # Django
   SECRET_KEY=<generar con: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
   DEBUG=0
   ALLOWED_HOSTS=zenzspa-web.onrender.com tudominio.com
   CSRF_TRUSTED_ORIGINS=https://zenzspa-web.onrender.com https://tudominio.com
   CORS_ALLOWED_ORIGINS=https://tudominio.com
   
   # Base de datos (copiar de PostgreSQL)
   DATABASE_URL=<Internal Database URL de Render>
   
   # Redis (copiar de Redis)
   REDIS_URL=<Internal Redis URL de Render>
   CELERY_BROKER_URL=<Internal Redis URL de Render>
   CELERY_RESULT_BACKEND=<Internal Redis URL de Render>
   
   # Twilio
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_VERIFY_SERVICE_SID=VA...
   
   # Wompi (PRODUCCIÓN)
   WOMPI_PUBLIC_KEY=pub_prod_...
   WOMPI_INTEGRITY_SECRET=prod_integrity_...
   WOMPI_EVENT_SECRET=prod_events_...
   WOMPI_REDIRECT_URL=https://tudominio.com/payment-result
   
   # Gemini
   GEMINI_API_KEY=...
   GEMINI_MODEL=gemini-1.5-flash
   BOT_GEMINI_TIMEOUT=20
   
   # Sentry
   SENTRY_DSN=https://...@sentry.io/...
   SENTRY_ENV=production
   SENTRY_TRACES_SAMPLE_RATE=0.1
   
   # Email (SendGrid)
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.sendgrid.net
   EMAIL_PORT=587
   EMAIL_USE_TLS=1
   EMAIL_HOST_USER=apikey
   EMAIL_HOST_PASSWORD=SG....
   DEFAULT_FROM_EMAIL=ZenzSpa <no-reply@tudominio.com>
   
   # Seguridad
   SECURE_SSL_REDIRECT=1
   HSTS_SECONDS=31536000
   
   # Rate Limiting (ajustado)
   THROTTLE_USER=100/min
   THROTTLE_ANON=30/min
   THROTTLE_BOT=5/min
   THROTTLE_BOT_DAILY=100/day
   ```

### **Paso 3.5: Crear Background Workers** ⏱️ 20 min

#### A. Celery Worker

1. Dashboard → New → Background Worker
2. Configuración:
   ```
   Name: zenzspa-worker
   Region: Oregon
   Build Command: ./build.sh
   Start Command: celery -A zenzspa worker -l info --concurrency=2
   Plan: Starter ($7/mes)
   ```
3. Copiar **todas** las environment variables del Web Service

#### B. Celery Beat

1. Dashboard → New → Background Worker
2. Configuración:
   ```
   Name: zenzspa-beat
   Region: Oregon
   Build Command: ./build.sh
   Start Command: celery -A zenzspa beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
   Plan: Starter ($7/mes)
   ```
3. Copiar **todas** las environment variables del Web Service

---

## FASE 4: DEPLOYMENT

### **Paso 4.1: Primer Deploy** ⏱️ 15-20 min

1. **Push a GitHub**:
   ```bash
   git add .
   git commit -m "feat: preparar para producción"
   git push origin main
   ```

2. **Render automáticamente**:
   - Detecta el push
   - Ejecuta build.sh
   - Despliega la aplicación

3. **Monitorear logs**:
   ```
   Dashboard → zenzspa-web → Logs
   
   Buscar:
   ✅ "Build completado!"
   ✅ "Starting gunicorn"
   ✅ "Listening at: http://0.0.0.0:8000"
   ```

### **Paso 4.2: Verificar Deployment** ⏱️ 30 min

#### A. Health Check Manual

```bash
# 1. Verificar que el servidor responde
curl https://zenzspa-web.onrender.com/admin/

# 2. Verificar API
curl https://zenzspa-web.onrender.com/api/v1/

# 3. Verificar que Redis funciona
# (Desde Render Shell)
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'hello')
>>> cache.get('test')
'hello'
```

#### B. Ejecutar Migraciones (si no se ejecutaron)

```bash
# Desde Render Shell
python manage.py migrate
python manage.py createsuperuser
```

#### C. Verificar Celery

```bash
# Logs de zenzspa-worker
# Debe mostrar:
# [tasks]
#   . spa.tasks.check_and_queue_reminders
#   . spa.tasks.cancel_unpaid_appointments
#   . bot.tasks.report_daily_token_usage
```

### **Paso 4.3: Configurar Dominio Personalizado** ⏱️ 1 hora

1. **En Render**:
   ```
   zenzspa-web → Settings → Custom Domain
   Agregar: api.tudominio.com
   ```

2. **En tu proveedor de DNS** (GoDaddy, Cloudflare, etc.):
   ```
   Tipo: CNAME
   Nombre: api
   Valor: zenzspa-web.onrender.com
   TTL: 3600
   ```

3. **Esperar propagación DNS** (5-30 minutos)

4. **Verificar SSL**:
   ```bash
   curl https://api.tudominio.com/admin/
   ```

---

## FASE 5: POST-DEPLOYMENT

### **Paso 5.1: Configurar Webhooks de Wompi** ⏱️ 15 min

1. **En dashboard de Wompi**:
   ```
   Configuración → Webhooks
   URL: https://api.tudominio.com/api/v1/payments/wompi-webhook/
   Eventos: transaction.updated
   ```

2. **Probar webhook**:
   ```bash
   # Hacer un pago de prueba pequeño
   # Verificar logs en Render
   ```

### **Paso 5.2: Smoke Tests en Producción** ⏱️ 1 hora

```bash
# Usar Postman con URL de producción

# 1. Registro de usuario
POST https://api.tudominio.com/api/v1/auth/register/

# 2. Verificación OTP
POST https://api.tudominio.com/api/v1/auth/verify-sms/

# 3. Login
POST https://api.tudominio.com/api/v1/auth/login/

# 4. Crear cita
POST https://api.tudominio.com/api/v1/appointments/

# 5. Pago (con monto pequeño real)
POST https://api.tudominio.com/api/v1/payments/

# 6. Bot
POST https://api.tudominio.com/api/v1/bot/message/

# 7. Analytics (staff)
GET https://api.tudominio.com/api/v1/analytics/kpis/
```

### **Paso 5.3: Configurar Monitoreo** ⏱️ 30 min

#### A. Sentry Alerts

```
Sentry → Alerts → Create Alert Rule

Condiciones:
- Error rate > 10 errors/min
- New issue created
- Regression (error que vuelve a aparecer)

Acciones:
- Email a tu correo
- Slack (opcional)
```

#### B. Render Notifications

```
Render → Account → Notifications

Habilitar:
- Deploy succeeded
- Deploy failed
- Service suspended
```

#### C. Uptime Monitoring (UptimeRobot - GRATIS)

```
1. Crear cuenta en uptimerobot.com
2. Agregar monitor:
   - Type: HTTPS
   - URL: https://api.tudominio.com/admin/
   - Interval: 5 minutos
3. Alertas por email si está caído
```

### **Paso 5.4: Backup de Base de Datos** ⏱️ 30 min

```bash
# Crear script de backup local
# scripts/backup_prod_db.sh

#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$HOME/zenzspa_backups"
mkdir -p $BACKUP_DIR

# Obtener DATABASE_URL de Render
DATABASE_URL="postgresql://..."

pg_dump $DATABASE_URL | gzip > $BACKUP_DIR/zenzspa_$DATE.sql.gz

# Mantener solo últimos 30 días
find $BACKUP_DIR -name "zenzspa_*.sql.gz" -mtime +30 -delete

echo "✅ Backup completado: zenzspa_$DATE.sql.gz"
```

```bash
# Agregar a crontab (ejecutar diariamente a las 2 AM)
crontab -e
0 2 * * * /path/to/scripts/backup_prod_db.sh
```

---

## FASE 6: MONITOREO Y MANTENIMIENTO

### **Checklist Diario** (5-10 min)

- [ ] Revisar Sentry para errores nuevos
- [ ] Verificar logs de Celery (tareas fallidas)
- [ ] Revisar uso de créditos de Gemini
- [ ] Verificar uptime (UptimeRobot)

### **Checklist Semanal** (30 min)

- [ ] Revisar métricas de performance (Sentry)
- [ ] Verificar uso de recursos (Render dashboard)
- [ ] Revisar logs de pagos (Wompi)
- [ ] Backup manual de DB
- [ ] Revisar analytics de uso

### **Checklist Mensual** (2 horas)

- [ ] Actualizar dependencias (security patches)
- [ ] Revisar y optimizar queries lentas
- [ ] Limpiar datos antiguos (logs, sesiones)
- [ ] Revisar costos de servicios
- [ ] Planear nuevas features

---

## TROUBLESHOOTING

### **Problema: Build falla en Render**

```bash
# Revisar logs de build
# Común: dependencias faltantes

# Solución:
# 1. Verificar requirements-prod.txt
# 2. Agregar dependencias del sistema en build.sh:
apt-get install -y libpq-dev gcc
```

### **Problema: Migraciones fallan**

```bash
# Error: "relation already exists"

# Solución:
python manage.py migrate --fake-initial
```

### **Problema: Celery no procesa tareas**

```bash
# Verificar:
# 1. REDIS_URL está configurado
# 2. Worker está corriendo
# 3. No hay errores en logs

# Reiniciar worker:
Render → zenzspa-worker → Manual Deploy → Deploy latest commit
```

### **Problema: Webhooks de Wompi no llegan**

```bash
# Verificar:
# 1. URL es HTTPS
# 2. Endpoint está accesible públicamente
# 3. Firma de webhook es correcta

# Test manual:
curl -X POST https://api.tudominio.com/api/v1/payments/wompi-webhook/ \
  -H "Content-Type: application/json" \
  -d '{"event": "transaction.updated", ...}'
```

### **Problema: Errores 500 en producción**

```bash
# 1. Revisar Sentry
# 2. Revisar logs de Render
# 3. Verificar variables de entorno
# 4. Verificar que DEBUG=0

# Logs en tiempo real:
Render → zenzspa-web → Logs → Live
```

---

## 💰 COSTOS ESTIMADOS MENSUALES

| Servicio | Plan | Costo |
|----------|------|-------|
| Render Web Service | Starter | $7/mes |
| Render PostgreSQL | Starter | $7/mes |
| Render Redis | Starter | $7/mes |
| Render Worker (Celery) | Starter | $7/mes |
| Render Beat | Starter | $7/mes |
| **Subtotal Render** | | **$35/mes** |
| Sentry | Free | $0 |
| SendGrid | Free (100/día) | $0 |
| Twilio | Pay-as-you-go | ~$5-10/mes |
| Gemini API | Pay-as-you-go | ~$5-15/mes |
| Dominio | Anual | ~$12/año |
| **TOTAL ESTIMADO** | | **$45-60/mes** |

---

## ✅ CHECKLIST FINAL PRE-LAUNCH

### Código
- [ ] Todas las mejoras críticas implementadas
- [ ] Tests unitarios >60% cobertura
- [ ] Tests de integración funcionando
- [ ] Colección de Postman completa
- [ ] Code review completo

### Configuración
- [ ] Variables de entorno configuradas
- [ ] Secretos rotados (no usar valores de desarrollo)
- [ ] ALLOWED_HOSTS configurado
- [ ] CORS configurado correctamente
- [ ] Rate limiting ajustado

### Servicios
- [ ] PostgreSQL funcionando
- [ ] Redis funcionando
- [ ] Celery Worker funcionando
- [ ] Celery Beat funcionando
- [ ] Sentry configurado
- [ ] SendGrid configurado

### Integraciones
- [ ] Twilio OTP funcionando
- [ ] Wompi pagos funcionando
- [ ] Webhooks de Wompi configurados
- [ ] Gemini bot funcionando

### Seguridad
- [ ] SSL/HTTPS habilitado
- [ ] HSTS configurado
- [ ] CSP configurado
- [ ] Logs sanitizados (sin secretos)
- [ ] Backup de DB configurado

### Monitoreo
- [ ] Sentry alertas configuradas
- [ ] Uptime monitoring configurado
- [ ] Logs accesibles
- [ ] Métricas de performance

---

## 🎯 PRÓXIMOS PASOS DESPUÉS DEL LAUNCH

1. **Semana 1**: Monitoreo intensivo, fix de bugs críticos
2. **Semana 2-4**: Implementar mejoras importantes
3. **Mes 2**: Optimizaciones de performance
4. **Mes 3**: Nuevas features basadas en feedback

---

## 📚 RECURSOS ADICIONALES

- [Documentación de Render](https://render.com/docs)
- [Guía de Django en Producción](https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/)
- [Sentry para Django](https://docs.sentry.io/platforms/python/guides/django/)
- [Celery Best Practices](https://docs.celeryproject.org/en/stable/userguide/tasks.html)

---

**¡Éxito con tu deployment! 🚀**

Si tienes dudas en cualquier paso, no dudes en preguntar.
