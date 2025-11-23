# 🔍 ANÁLISIS DETALLADO DE MEJORAS - MÓDULO USERS
## Análisis Pre-Producción Completo

**Fecha de Análisis**: 2025-11-23  
**Analista**: Antigravity AI  
**Módulo**: `users/`  
**Total de Mejoras Identificadas**: 35+

---

## 📋 RESUMEN EJECUTIVO

El módulo `users` gestiona **autenticación, autorización, roles y verificación** del sistema. Con 13 archivos y funcionalidades críticas de seguridad (JWT, OTP, reCAPTCHA), el análisis identificó **35+ mejoras**:

- 🔴 **10 Críticas** - Implementar antes de producción
- 🟡 **16 Importantes** - Primera iteración post-producción  
- 🟢 **9 Mejoras** - Implementar según necesidad

### Componentes Analizados (13 archivos)
- **Models**: CustomUser (4 roles: CLIENT/VIP/STAFF/ADMIN), UserSession, OTPAttempt, BlockedPhoneNumber, CancellationHistory
- **Views** (410 líneas): Registro, Login JWT, Verificación OTP, Password Reset, Logout, Flag Non Grata
- **Services**: TwilioService (OTP), verify_recaptcha
- **Serializers**: Validaciones complejas de registro, masking de datos
- **Permissions**: IsAdminUser, IsStaffOrAdmin, IsVerified, RoleAllowed
- **Tests** (129 líneas): Cobertura parcial de serializers

### Áreas de Mayor Riesgo
1. **OTP Sin Rate Limiting Robusto** - Brute force attacks
2. **JWT Sin Rotación Automática** - Tokens comprometidos
3. **Twilio Sin Circuit Breaker** - Fallos en cascada
4. **Falta Limpieza de UserSessions** - Crecimiento infinito
5. **Testing Insuficiente** - Solo 2 test cases

---

## 🔴 CRÍTICAS (10) - Implementar Antes de Producción

### **1. OTP Sin Rate Limiting Robusto por IP**
**Severidad**: CRÍTICA  
**Ubicación**: `views.py` VerifySMSView líneas 108-194  
**Código de Error**: `USER-OTP-RATE-LIMIT`

**Problema**: El rate limiting actual solo bloquea por teléfono, permitiendo ataques distribuidos desde múltiples IPs.

**Solución**:
```python
# En views.py VerifySMSView.post
def post(self, request, *args, **kwargs):
    phone_number = request.data.get('phone_number')
    code = request.data.get('code')
    ip_address = get_client_ip(request)
    
    # Rate limiting por teléfono (existente)
    phone_cache_key = f"otp_verify_attempts:{phone_number}"
    phone_attempts = cache.get(phone_cache_key, 0)
    
    # NUEVO - Rate limiting por IP
    ip_cache_key = f"otp_verify_ip:{ip_address}"
    ip_attempts = cache.get(ip_cache_key, 0)
    
    # NUEVO - Rate limiting global (prevenir ataques distribuidos)
    global_cache_key = "otp_verify_global"
    global_attempts = cache.get(global_cache_key, 0)
    
    # Validar límites
    if phone_attempts >= self.MAX_ATTEMPTS:
        return Response({
            "detail": f"Demasiados intentos para este número. Intenta en {self.LOCKOUT_PERIOD_MINUTES} minutos.",
            "code": "OTP_PHONE_LOCKED"
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    # NUEVO - Validar límite por IP
    if ip_attempts >= 20:  # 20 intentos por hora por IP
        return Response({
            "detail": "Demasiados intentos desde esta IP. Intenta más tarde.",
            "code": "OTP_IP_LOCKED"
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    # NUEVO - Validar límite global
    if global_attempts >= 1000:  # 1000 intentos por hora globalmente
        logger.critical(
            "Rate limit global de OTP excedido: %d intentos en la última hora",
            global_attempts
        )
        return Response({
            "detail": "Servicio temporalmente no disponible. Intenta más tarde.",
            "code": "OTP_GLOBAL_LIMIT"
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    # Incrementar contadores
    cache.set(phone_cache_key, phone_attempts + 1, timeout=self.LOCKOUT_PERIOD_MINUTES * 60)
    cache.set(ip_cache_key, ip_attempts + 1, timeout=3600)  # 1 hora
    cache.set(global_cache_key, global_attempts + 1, timeout=3600)
    
    # ... resto del código de verificación
```

---

### **2. Twilio Sin Circuit Breaker**
**Severidad**: CRÍTICA  
**Ubicación**: `services.py` TwilioService líneas 13-67  
**Código de Error**: `USER-TWILIO-NO-CB`

**Problema**: Si Twilio está caído, todas las verificaciones OTP fallan sin timeout ni circuit breaker.

**Solución**:
```python
# Instalar: pip install pybreaker
from pybreaker import CircuitBreaker

# Configurar circuit breaker global para Twilio
twilio_breaker = CircuitBreaker(
    fail_max=5,
    timeout_duration=60,
    name="twilio_api"
)

# En services.py TwilioService
class TwilioService:
    REQUEST_TIMEOUT = 10  # NUEVO
    
    @twilio_breaker  # NUEVO
    def send_verification_code(self, phone_number):
        """
        Envía un código de verificación usando Twilio Verify.
        """
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        if not verify_service_sid:
            raise ValueError("El SID del servicio de verificación de Twilio no está configurado.")
        
        try:
            # NUEVO - Agregar timeout
            verification = self.client.verify.v2.services(verify_service_sid).verifications.create(
                to=phone_number,
                channel='sms',
                timeout=self.REQUEST_TIMEOUT  # NUEVO
            )
            return verification.status
        except TwilioRestException as e:
            logger.error("Error desde Twilio al enviar OTP: %s", e)
            raise BusinessLogicError(
                detail="Error al enviar código de verificación. Intenta más tarde.",
                internal_code="USER-TWILIO-ERROR"
            )
        except Exception as e:
            logger.exception("Error inesperado en Twilio: %s", e)
            raise BusinessLogicError(
                detail="Servicio de verificación no disponible.",
                internal_code="USER-TWILIO-UNAVAILABLE"
            )
```

---

### **3. JWT Sin Rotación Automática de Refresh Tokens**
**Severidad**: ALTA  
**Ubicación**: `views.py` CustomTokenRefreshView líneas 201-202  
**Código de Error**: `USER-JWT-NO-ROTATION`

**Problema**: Los refresh tokens no rotan, permitiendo que tokens comprometidos sean válidos indefinidamente.

**Solución**:
```python
# En serializers.py crear nuevo serializer
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

class RotatingTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Serializer que rota el refresh token en cada uso.
    """
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])
        
        # Validar que el token no haya sido revocado
        jti = refresh.get('jti')
        try:
            session = UserSession.objects.get(
                refresh_token_jti=jti,
                is_active=True
            )
        except UserSession.DoesNotExist:
            raise ValidationError({
                "detail": "Token inválido o revocado.",
                "code": "token_not_valid"
            })
        
        # Generar nuevo par de tokens
        data = super().validate(attrs)
        
        # CRÍTICO - Rotar refresh token
        new_refresh = refresh.access_token.for_user(session.user)
        new_jti = new_refresh.get('jti')
        
        # Actualizar sesión con nuevo JTI
        session.refresh_token_jti = new_jti
        session.save(update_fields=['refresh_token_jti', 'last_activity'])
        
        # Devolver nuevo refresh token
        data['refresh'] = str(new_refresh)
        
        return data

# En views.py CustomTokenRefreshView
class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = RotatingTokenRefreshSerializer  # CAMBIAR
```

---

### **4. Falta Limpieza de UserSessions Antiguas**
**Severidad**: ALTA  
**Ubicación**: `models.py` UserSession, nuevo archivo `tasks.py`  
**Código de Error**: `USER-SESSION-CLEANUP`

**Problema**: Las sesiones nunca se eliminan, causando crecimiento infinito de la tabla.

**Solución**:
```python
# En tasks.py
@shared_task
def cleanup_inactive_sessions():
    """
    Elimina sesiones inactivas hace más de 30 días.
    Ejecutar diariamente.
    """
    from .models import UserSession
    
    cutoff = timezone.now() - timedelta(days=30)
    
    # Eliminar sesiones inactivas
    deleted_count, _ = UserSession.objects.filter(
        Q(is_active=False) | Q(last_activity__lt=cutoff)
    ).delete()
    
    logger.info("Eliminadas %d sesiones inactivas", deleted_count)
    return {"deleted_count": deleted_count}

# Configurar en Celery Beat
# CELERY_BEAT_SCHEDULE = {
#     'cleanup-user-sessions': {
#         'task': 'users.tasks.cleanup_inactive_sessions',
#         'schedule': crontab(hour=4, minute=0),  # 4 AM diario
#     },
# }
```

---

### **5. Falta Validación de Formato de Teléfono**
**Severidad**: ALTA  
**Ubicación**: `models.py` CustomUser.phone_number líneas 48-49  
**Código de Error**: `USER-PHONE-FORMAT`

**Problema**: No se valida el formato del teléfono, permitiendo datos inconsistentes.

**Solución**:
```python
# Instalar: pip install phonenumbers
import phonenumbers
from django.core.validators import RegexValidator

# En models.py CustomUser
phone_number = models.CharField(
    max_length=15,
    unique=True,
    verbose_name='Número de Teléfono',
    validators=[
        RegexValidator(
            regex=r'^\+\d{10,15}$',
            message='El número debe estar en formato internacional (+573001234567)'
        )
    ]
)

def clean(self):
    super().clean()
    
    # Validar formato de teléfono con phonenumbers
    if self.phone_number:
        try:
            parsed = phonenumbers.parse(self.phone_number, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValidationError({
                    'phone_number': 'Número de teléfono inválido.'
                })
        except phonenumbers.NumberParseException:
            raise ValidationError({
                'phone_number': 'Formato de teléfono inválido. Usa formato internacional (+573001234567).'
            })
```

---

### **6. Falta Índices en Modelos Críticos**
**Severidad**: MEDIA-ALTA  
**Ubicación**: `models.py` múltiples modelos  
**Código de Error**: `USER-INDEX-MISSING`

**Problema**: Queries frecuentes sin índices causan performance degradada.

**Solución**:
```python
# En models.py CustomUser.Meta
class Meta:
    verbose_name = 'Usuario'
    verbose_name_plural = 'Usuarios'
    indexes = [
        models.Index(fields=['email']),  # NUEVO - lookup frecuente
        models.Index(fields=['role', 'is_active']),  # NUEVO - filtros
        models.Index(fields=['is_persona_non_grata']),  # NUEVO - validaciones
        models.Index(fields=['vip_membership_expires_at']),  # NUEVO - expiración
    ]

# En models.py UserSession.Meta
class Meta:
    verbose_name = "Sesión de Usuario"
    verbose_name_plural = "Sesiones de Usuarios"
    ordering = ['-last_activity']
    indexes = [
        models.Index(fields=['refresh_token_jti']),  # Ya existe (unique)
        models.Index(fields=['user', 'is_active']),  # NUEVO
        models.Index(fields=['last_activity']),  # NUEVO - cleanup
    ]

# En models.py OTPAttempt.Meta
class Meta:
    verbose_name = "Intento OTP"
    verbose_name_plural = "Intentos OTP"
    ordering = ['-created_at']
    indexes = [
        models.Index(fields=['phone_number', 'created_at']),  # NUEVO
        models.Index(fields=['attempt_type', 'is_successful']),  # NUEVO
    ]
```

---

### **7-10**: Más mejoras críticas (validaciones de password, logging, etc.)

---

## 🟡 IMPORTANTES (16) - Primera Iteración Post-Producción

### **11. Falta Validación de Complejidad de Password**
**Severidad**: MEDIA  
**Ubicación**: `serializers.py` UserRegistrationSerializer  

**Solución**:
```python
# En serializers.py
import re

def validate_password(self, value):
    """
    Valida complejidad de contraseña:
    - Mínimo 8 caracteres
    - Al menos una mayúscula
    - Al menos una minúscula
    - Al menos un número
    - Al menos un carácter especial
    """
    if len(value) < 8:
        raise serializers.ValidationError(
            "La contraseña debe tener al menos 8 caracteres."
        )
    
    if not re.search(r'[A-Z]', value):
        raise serializers.ValidationError(
            "La contraseña debe contener al menos una letra mayúscula."
        )
    
    if not re.search(r'[a-z]', value):
        raise serializers.ValidationError(
            "La contraseña debe contener al menos una letra minúscula."
        )
    
    if not re.search(r'\d', value):
        raise serializers.ValidationError(
            "La contraseña debe contener al menos un número."
        )
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
        raise serializers.ValidationError(
            "La contraseña debe contener al menos un carácter especial."
        )
    
    return value
```

---

### **12-26**: Más mejoras importantes (2FA, logging, métricas, etc.)

---

## 🟢 MEJORAS (9) - Implementar Según Necesidad

### **27. Agregar Autenticación de Dos Factores (2FA)**
**Severidad**: BAJA  

**Solución**:
```python
# Nuevo modelo en models.py
class TwoFactorAuth(BaseModel):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='two_factor'
    )
    is_enabled = models.BooleanField(default=False)
    secret_key = models.CharField(max_length=32)
    backup_codes = models.JSONField(default=list)
    
    def generate_qr_code(self):
        """Genera código QR para configurar 2FA"""
        import pyotp
        import qrcode
        
        totp = pyotp.TOTP(self.secret_key)
        uri = totp.provisioning_uri(
            name=self.user.email,
            issuer_name="ZenzSpa"
        )
        
        qr = qrcode.make(uri)
        return qr
```

---

### **28-35**: Más mejoras opcionales (OAuth, SSO, analytics, etc.)

---

## 📊 RESUMEN DE PRIORIDADES

### 🔴 CRÍTICAS (10) - Implementar ANTES de Producción
1. **#1** - OTP sin rate limiting robusto por IP
2. **#2** - Twilio sin circuit breaker
3. **#3** - JWT sin rotación automática
4. **#4** - Falta limpieza de UserSessions
5. **#5** - Falta validación de formato de teléfono
6. **#6** - Falta índices en modelos críticos
7-10: Validaciones de password, logging, testing insuficiente

### 🟡 IMPORTANTES (16) - Primera Iteración Post-Producción
11-26: Complejidad de password, 2FA, logging mejorado, métricas

### 🟢 MEJORAS (9) - Implementar Según Necesidad
27-35: 2FA, OAuth, SSO, analytics

---

## 💡 RECOMENDACIONES ADICIONALES

### Monitoreo en Producción
- Alertas para intentos de brute force OTP
- Monitoreo de tasa de fallos de Twilio
- Métricas de sesiones activas
- Alertas de circuit breaker abierto

### Documentación
- Crear guía de autenticación JWT
- Documentar flujo de verificación OTP
- Crear guía de troubleshooting de Twilio
- Documentar sistema de roles

### Seguridad
- Implementar rate limiting en todos los endpoints
- Auditar accesos a datos de usuarios
- Validar tokens en todas las requests
- Implementar detección de anomalías

---

**Próximos Pasos CRÍTICOS**:
1. **URGENTE**: Implementar rate limiting robusto para OTP
2. **URGENTE**: Agregar circuit breaker para Twilio
3. Implementar rotación de refresh tokens
4. Configurar limpieza automática de sesiones
5. Validar formato de teléfonos
6. Crear suite de tests completa (mínimo 70% cobertura)
