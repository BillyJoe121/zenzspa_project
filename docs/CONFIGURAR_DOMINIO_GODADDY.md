# 🌐 GUÍA: CONECTAR DOMINIO DE GODADDY CON RENDER

**Fecha**: 2025-11-23  
**Objetivo**: Configurar dominio personalizado para studiozens en Render

---

## 📋 INFORMACIÓN QUE NECESITAS

Antes de empezar, ten a mano:
- ✅ Tu dominio de GoDaddy (ejemplo: `studiozens.com`)
- ✅ Acceso a tu cuenta de GoDaddy
- ✅ Acceso a tu cuenta de Render
- ✅ URL de tu servicio en Render (ejemplo: `studiozens-web.onrender.com`)

---

## 🎯 ARQUITECTURA RECOMENDADA

Para un proyecto como studiozens, te recomiendo esta estructura:

```
tudominio.com                    → Frontend (si tienes)
www.tudominio.com                → Redirect a tudominio.com
api.tudominio.com                → Backend Django (Render)
admin.tudominio.com              → Django Admin (mismo backend)
```

**Para este tutorial, vamos a configurar `api.tudominio.com`** para tu backend.

---

## PASO 1: CONFIGURAR EN RENDER (5 minutos)

### 1.1 Agregar Custom Domain

1. **Ir a tu Web Service en Render**:
   ```
   Dashboard → studiozens-web → Settings
   ```

2. **Scroll hasta "Custom Domains"**:
   ```
   Click en "Add Custom Domain"
   ```

3. **Agregar tu subdominio**:
   ```
   Domain: api.tudominio.com
   
   Click "Save"
   ```

4. **Render te mostrará instrucciones DNS**:
   ```
   Verás algo como:
   
   Type: CNAME
   Name: api
   Value: studiozens-web.onrender.com
   
   ⚠️ IMPORTANTE: Copia exactamente estos valores
   ```

---

## PASO 2: CONFIGURAR DNS EN GODADDY (10 minutos)

### 2.1 Acceder a DNS Management

1. **Ir a GoDaddy**:
   ```
   https://dcc.godaddy.com/
   ```

2. **Seleccionar tu dominio**:
   ```
   My Products → Domains → [tu dominio] → DNS
   ```

3. **Verás la página de DNS Management**

### 2.2 Agregar Registro CNAME para API

1. **Click en "Add" (Agregar)**

2. **Configurar el registro**:
   ```
   Type: CNAME
   Name: api
   Value: studiozens-web.onrender.com
   TTL: 1 Hour (o 3600 segundos)
   ```

3. **Click "Save"**

### 2.3 (Opcional) Configurar Dominio Principal

Si quieres que `tudominio.com` también apunte a tu backend:

1. **Agregar registro A**:
   ```
   Type: A
   Name: @ (representa el dominio raíz)
   Value: [IP de Render - la obtienes haciendo ping a studiozens-web.onrender.com]
   TTL: 1 Hour
   ```

2. **Agregar registro CNAME para www**:
   ```
   Type: CNAME
   Name: www
   Value: tudominio.com
   TTL: 1 Hour
   ```

---

## PASO 3: VERIFICAR CONFIGURACIÓN (30-60 minutos)

### 3.1 Esperar Propagación DNS

⏱️ **Tiempo de espera**: 5 minutos a 48 horas (usualmente 15-30 minutos)

**Verificar propagación**:
```bash
# En tu terminal (PowerShell)
nslookup api.tudominio.com

# Deberías ver algo como:
# Name:    studiozens-web.onrender.com
# Address: [IP de Render]
```

**Herramienta online**:
```
https://dnschecker.org/
Buscar: api.tudominio.com
Tipo: CNAME
```

### 3.2 Verificar en Render

1. **Volver a Render**:
   ```
   Dashboard → studiozens-web → Settings → Custom Domains
   ```

2. **Verificar estado**:
   ```
   api.tudominio.com
   Status: ✅ Verified (puede tardar)
   
   Si dice "Pending", espera unos minutos y refresca
   ```

### 3.3 Verificar SSL/HTTPS

Render automáticamente genera certificado SSL (Let's Encrypt):

```bash
# Verificar que HTTPS funciona
curl https://api.tudominio.com/admin/

# Deberías ver el HTML del admin de Django
```

---

## PASO 4: ACTUALIZAR VARIABLES DE ENTORNO EN RENDER

⚠️ **CRÍTICO**: Debes actualizar las variables de entorno para incluir tu dominio.

### 4.1 Actualizar ALLOWED_HOSTS

```
Dashboard → studiozens-web → Environment → Edit

ALLOWED_HOSTS=studiozens-web.onrender.com,api.tudominio.com,tudominio.com
```

### 4.2 Actualizar CSRF_TRUSTED_ORIGINS

```
CSRF_TRUSTED_ORIGINS=https://studiozens-web.onrender.com,https://api.tudominio.com,https://tudominio.com
```

### 4.3 Actualizar CORS_ALLOWED_ORIGINS

```
CORS_ALLOWED_ORIGINS=https://api.tudominio.com,https://tudominio.com,https://tufrontend.com
```

### 4.4 Actualizar WOMPI_REDIRECT_URL

```
WOMPI_REDIRECT_URL=https://tudominio.com/payment-result
```

### 4.5 Guardar y Re-deploy

```
Click "Save Changes"

Render automáticamente re-desplegará tu aplicación
```

---

## PASO 5: VERIFICAR TODO FUNCIONA

### 5.1 Test Básico

```bash
# 1. Verificar admin
https://api.tudominio.com/admin/

# 2. Verificar API
https://api.tudominio.com/api/v1/

# 3. Verificar que HTTPS funciona (candado verde en navegador)
```

### 5.2 Test con Postman

Actualizar tu colección de Postman:

```
Variable: base_url
Valor: https://api.tudominio.com
```

Ejecutar todos los tests para verificar que funcionan.

### 5.3 Test de Webhooks

Si ya configuraste webhooks de Wompi, actualízalos:

```
Dashboard de Wompi → Webhooks
URL: https://api.tudominio.com/api/v1/payments/wompi-webhook/
```

---

## CONFIGURACIONES ADICIONALES RECOMENDADAS

### Opción 1: Redirect de www a dominio principal

En GoDaddy:

```
Type: CNAME
Name: www
Value: tudominio.com
TTL: 1 Hour
```

### Opción 2: Subdominio para Admin

Si quieres un subdominio separado para el admin:

1. **En Render**: Agregar `admin.tudominio.com` como custom domain
2. **En GoDaddy**: 
   ```
   Type: CNAME
   Name: admin
   Value: studiozens-web.onrender.com
   TTL: 1 Hour
   ```

### Opción 3: Configurar Email con tu Dominio

Para enviar emails desde `no-reply@tudominio.com`:

1. **En SendGrid**:
   ```
   Settings → Sender Authentication → Domain Authentication
   Dominio: tudominio.com
   ```

2. **SendGrid te dará registros DNS** (CNAME, TXT)

3. **Agregar en GoDaddy**:
   ```
   Copiar los registros que SendGrid te proporciona
   Agregarlos en DNS Management
   ```

4. **Verificar en SendGrid** (puede tardar 24-48h)

---

## TROUBLESHOOTING

### ❌ Error: "DNS_PROBE_FINISHED_NXDOMAIN"

**Causa**: DNS aún no ha propagado

**Solución**:
```bash
# Esperar más tiempo (hasta 48h)
# Verificar en dnschecker.org
# Verificar que el registro CNAME está correcto en GoDaddy
```

### ❌ Error: "This site can't provide a secure connection"

**Causa**: SSL aún no está configurado

**Solución**:
```
1. Esperar que Render genere el certificado (5-30 min)
2. Verificar en Render que el dominio está "Verified"
3. Forzar renovación: Render → Settings → Custom Domains → Renew Certificate
```

### ❌ Error: "DisallowedHost at /"

**Causa**: Falta agregar el dominio a ALLOWED_HOSTS

**Solución**:
```
Render → Environment → ALLOWED_HOSTS
Agregar: api.tudominio.com
Save → Re-deploy
```

### ❌ Error: "CSRF verification failed"

**Causa**: Falta agregar el dominio a CSRF_TRUSTED_ORIGINS

**Solución**:
```
Render → Environment → CSRF_TRUSTED_ORIGINS
Agregar: https://api.tudominio.com
Save → Re-deploy
```

### ❌ Propagación DNS muy lenta

**Solución**:
```bash
# Limpiar caché DNS local (PowerShell como Admin)
ipconfig /flushdns

# Usar DNS de Google temporalmente
# Configuración de red → Propiedades IPv4 → DNS
# Preferido: 8.8.8.8
# Alternativo: 8.8.4.4
```

---

## CHECKLIST FINAL

- [ ] Registro CNAME creado en GoDaddy
- [ ] DNS propagado (verificado con dnschecker.org)
- [ ] Dominio verificado en Render
- [ ] SSL/HTTPS funcionando (candado verde)
- [ ] ALLOWED_HOSTS actualizado
- [ ] CSRF_TRUSTED_ORIGINS actualizado
- [ ] CORS_ALLOWED_ORIGINS actualizado
- [ ] WOMPI_REDIRECT_URL actualizado
- [ ] Tests de Postman funcionando
- [ ] Webhooks de Wompi actualizados
- [ ] Admin accesible en https://api.tudominio.com/admin/

---

## CONFIGURACIÓN COMPLETA DE EJEMPLO

### GoDaddy DNS Records

```
Type    Name    Value                           TTL
A       @       [IP de Render]                  1 Hour
CNAME   www     tudominio.com                   1 Hour
CNAME   api     studiozens-web.onrender.com        1 Hour
CNAME   admin   studiozens-web.onrender.com        1 Hour
```

### Render Environment Variables

```bash
# Hosts y CORS
ALLOWED_HOSTS=studiozens-web.onrender.com,api.tudominio.com,admin.tudominio.com,tudominio.com,www.tudominio.com
CSRF_TRUSTED_ORIGINS=https://studiozens-web.onrender.com,https://api.tudominio.com,https://admin.tudominio.com,https://tudominio.com,https://www.tudominio.com
CORS_ALLOWED_ORIGINS=https://tudominio.com,https://www.tudominio.com,https://api.tudominio.com

# Wompi
WOMPI_REDIRECT_URL=https://tudominio.com/payment-result

# Email
DEFAULT_FROM_EMAIL=StudioZens <no-reply@tudominio.com>
```

---

## PRÓXIMOS PASOS

1. ✅ **Configurar dominio** (acabas de hacer esto)
2. ⏭️ **Configurar email** (opcional - SendGrid domain authentication)
3. ⏭️ **Configurar frontend** (si tienes) en `tudominio.com`
4. ⏭️ **Configurar CDN** (Cloudflare - opcional pero recomendado)

---

## RECURSOS ADICIONALES

- [Documentación de Render - Custom Domains](https://render.com/docs/custom-domains)
- [GoDaddy - Manage DNS](https://www.godaddy.com/help/manage-dns-680)
- [DNS Checker](https://dnschecker.org/)
- [SSL Labs - Test SSL](https://www.ssllabs.com/ssltest/)

---

**¡Tu dominio está listo! 🎉**

Ahora puedes acceder a tu API en `https://api.tudominio.com`
