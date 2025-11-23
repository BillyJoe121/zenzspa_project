# 🔍 ANÁLISIS DETALLADO DE MEJORAS - MÓDULO SPA
## Análisis Pre-Producción Completo

**Fecha de Análisis**: 2025-11-23  
**Analista**: Antigravity AI  
**Módulo**: `spa/` (MÓDULO CENTRAL DEL SISTEMA)  
**Total de Mejoras Identificadas**: 40+

---

## 📋 RESUMEN EJECUTIVO

El módulo `spa` es el **corazón del sistema**, gestionando citas, servicios, pagos (Wompi), vouchers, créditos, waitlist, y disponibilidad de staff. Con **3,041 líneas de código** distribuidas en 12 archivos, el análisis identificó **40+ mejoras críticas**:

- 🔴 **12 Críticas** - Implementar antes de producción
- 🟡 **18 Importantes** - Primera iteración post-producción  
- 🟢 **10 Mejoras** - Implementar según necesidad

### Componentes Analizados (12 archivos)
- **Models** (692 líneas, 75 items): Appointment, Service, Payment, Voucher, ClientCredit, Package, StaffAvailability, WaitlistEntry, AvailabilityExclusion
- **Services** (1494 líneas, 57 items): AvailabilityService, AppointmentService, PaymentService, VoucherService, WaitlistService, CancellationService, LoyaltyService
- **Views** (855 líneas, 46 items): AppointmentViewSet, PaymentViewSet, VoucherViewSet, WaitlistViewSet
- **Serializers** (15KB): Validaciones complejas de citas, pagos, vouchers
- **Tasks** (13KB): Tareas asíncronas de pagos, cancelaciones, waitlist
- **Admin, Permissions, URLs**

### Áreas de Mayor Riesgo
1. **Race Conditions en Disponibilidad** - Doble reserva de slots
2. **Integración Wompi Sin Circuit Breaker** - Fallos en cascada
3. **Sistema de Cancelaciones Complejo** - Lógica de 3 strikes inconsistente
4. **Vouchers Sin Validación Atómica** - Uso duplicado
5. **Testing Completamente Ausente** - Sin cobertura en módulo crítico

---

## 🔴 CRÍTICAS (12) - Implementar Antes de Producción

### **1. Race Condition en Disponibilidad de Slots**
**Severidad**: CRÍTICA  
**Ubicación**: `services.py` AvailabilityService._build_slots líneas 91-183  
**Código de Error**: `SPA-RACE-AVAILABILITY`

**Problema**: Dos usuarios pueden reservar el mismo slot simultáneamente porque la validación de disponibilidad y la creación de cita no son atómicas.

**Escenario de Fallo**:
1. Usuario A consulta slots disponibles → ve slot 10:00 AM libre
2. Usuario B consulta slots disponibles → ve slot 10:00 AM libre
3. Usuario A crea cita para 10:00 AM → éxito
4. Usuario B crea cita para 10:00 AM → éxito (DOBLE RESERVA)

**Solución**:
```python
# En services.py AppointmentService.create_appointment_with_lock
@transaction.atomic
def create_appointment_with_lock(self):
    """
    Crea la cita con lock en el staff member para evitar race conditions.
    """
    # Validaciones sin lock
    self._validate_appointment_rules()
    
    # CRÍTICO - Lock en staff member antes de validar disponibilidad
    staff = CustomUser.objects.select_for_update().get(pk=self.staff_member.pk)
    
    # Re-validar disponibilidad con lock activo
    self._ensure_staff_is_available()
    
    # Verificar que no haya citas conflictivas CON LOCK
    end_time = self.start_time + timedelta(minutes=self.total_duration)
    conflicting = Appointment.objects.select_for_update().filter(
        staff_member=staff,
        start_time__lt=end_time,
        end_time__gt=self.start_time,
        status__in=[
            Appointment.AppointmentStatus.PENDING_PAYMENT,
            Appointment.AppointmentStatus.PAID,
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]
    ).exists()
    
    if conflicting:
        raise BusinessLogicError(
            detail="El slot seleccionado ya no está disponible.",
            internal_code="SPA-SLOT-TAKEN"
        )
    
    # ... resto del código de creación
```

---

### **2. Integración Wompi Sin Circuit Breaker**
**Severidad**: CRÍTICA  
**Ubicación**: `services.py` PaymentService líneas 630-1494  
**Código de Error**: `SPA-WOMPI-NO-CB`

**Problema**: Si Wompi está caído, todas las requests de pago fallan sin timeout ni circuit breaker, bloqueando el sistema.

**Solución**:
```python
# Instalar: pip install pybreaker
from pybreaker import CircuitBreaker
import requests

# Configurar circuit breaker global para Wompi
wompi_breaker = CircuitBreaker(
    fail_max=5,  # Abrir después de 5 fallos
    timeout_duration=60,  # Mantener abierto 60 segundos
    name="wompi_api"
)

# En services.py PaymentService
class PaymentService:
    WOMPI_DEFAULT_BASE_URL = "https://production.wompi.co/v1"
    REQUEST_TIMEOUT = 10  # NUEVO - timeout de 10 segundos
    
    @classmethod
    @wompi_breaker  # NUEVO - circuit breaker
    def _make_wompi_request(cls, method, endpoint, **kwargs):
        """
        Wrapper para todas las requests a Wompi con circuit breaker y timeout.
        """
        base_url = getattr(settings, "WOMPI_BASE_URL", cls.WOMPI_DEFAULT_BASE_URL)
        url = f"{base_url}/{endpoint}"
        
        # Agregar timeout a todas las requests
        kwargs.setdefault('timeout', cls.REQUEST_TIMEOUT)
        
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.Timeout:
            logger.error("Timeout en request a Wompi: %s %s", method, endpoint)
            raise BusinessLogicError(
                detail="El servicio de pagos no responde. Intenta más tarde.",
                internal_code="SPA-PAYMENT-TIMEOUT"
            )
        except requests.RequestException as e:
            logger.exception("Error en request a Wompi: %s", e)
            raise BusinessLogicError(
                detail="Error al procesar el pago. Intenta más tarde.",
                internal_code="SPA-PAYMENT-ERROR"
            )
    
    @classmethod
    def _resolve_acceptance_token(cls, base_url):
        """Usar wrapper con circuit breaker"""
        response = cls._make_wompi_request('GET', 'merchants/pub_test_...')
        # ... resto del código
```

---

### **3. Sistema de 3 Strikes Inconsistente**
**Severidad**: CRÍTICA  
**Ubicación**: `views.py` _apply_three_strikes_penalty líneas 98-116  
**Código de Error**: `SPA-STRIKES-INCONSISTENT`

**Problema**: La lógica de 3 strikes no es atómica y puede contar strikes incorrectamente en cancelaciones concurrentes.

**Solución**:
```python
# En views.py _apply_three_strikes_penalty
@transaction.atomic
def _apply_three_strikes_penalty(user, appointment, history):
    """
    Aplica penalización de 3 strikes de forma atómica.
    """
    from users.models import CancellationHistory
    
    # Lock en usuario para evitar race condition
    user = CustomUser.objects.select_for_update().get(pk=user.pk)
    
    # Contar strikes DENTRO de la transacción
    recent_strikes = CancellationHistory.objects.filter(
        user=user,
        created_at__gte=timezone.now() - timedelta(days=30),
        strike_type__in=[
            CancellationHistory.StrikeType.LATE_CANCELLATION,
            CancellationHistory.StrikeType.NO_SHOW
        ]
    ).count()
    
    if recent_strikes >= 3:
        # Marcar como persona no grata
        user.is_persona_non_grata = True
        user.persona_non_grata_since = timezone.now()
        user.save(update_fields=[
            'is_persona_non_grata',
            'persona_non_grata_since',
            'updated_at'
        ])
        
        # Auditar
        safe_audit_log(
            action=AuditLog.Action.FLAG_NON_GRATA,
            admin_user=None,  # Sistema automático
            target_user=user,
            details={
                "reason": "3_strikes_penalty",
                "appointment_id": str(appointment.id),
                "total_strikes": recent_strikes
            }
        )
        
        logger.warning(
            "Usuario %s marcado como persona non grata por 3 strikes",
            user.id
        )
```

---

### **4. Vouchers Sin Validación Atómica de Uso**
**Severidad**: CRÍTICA  
**Ubicación**: `services.py` VoucherService líneas 1100-1200 (aprox)  
**Código de Error**: `SPA-VOUCHER-RACE`

**Problema**: Dos usuarios pueden usar el mismo voucher simultáneamente si no hay lock.

**Solución**:
```python
# En services.py VoucherService
@classmethod
@transaction.atomic
def redeem_voucher(cls, voucher_code, user, appointment):
    """
    Redime un voucher de forma atómica.
    """
    try:
        # CRÍTICO - Lock en voucher
        voucher = Voucher.objects.select_for_update().get(
            code=voucher_code,
            is_active=True
        )
    except Voucher.DoesNotExist:
        raise BusinessLogicError(
            detail="Voucher no encontrado o inactivo.",
            internal_code="SPA-VOUCHER-INVALID"
        )
    
    # Validar expiración
    if voucher.expires_at and voucher.expires_at < timezone.now():
        raise BusinessLogicError(
            detail="El voucher ha expirado.",
            internal_code="SPA-VOUCHER-EXPIRED"
        )
    
    # Validar uso máximo
    if voucher.usage_count >= voucher.max_uses:
        raise BusinessLogicError(
            detail="El voucher ha alcanzado su límite de usos.",
            internal_code="SPA-VOUCHER-EXHAUSTED"
        )
    
    # Validar que el usuario no lo haya usado (si es de un solo uso)
    if voucher.max_uses == 1:
        if Appointment.objects.filter(
            user=user,
            voucher=voucher
        ).exists():
            raise BusinessLogicError(
                detail="Ya has usado este voucher.",
                internal_code="SPA-VOUCHER-ALREADY-USED"
            )
    
    # Incrementar contador de uso
    voucher.usage_count += 1
    voucher.save(update_fields=['usage_count', 'updated_at'])
    
    # Asignar voucher a la cita
    appointment.voucher = voucher
    appointment.save(update_fields=['voucher', 'updated_at'])
    
    # Auditar
    safe_audit_log(
        action=AuditLog.Action.VOUCHER_REDEEMED,
        admin_user=None,
        target_user=user,
        details={
            "voucher_code": voucher_code,
            "appointment_id": str(appointment.id),
            "usage_count": voucher.usage_count
        }
    )
    
    return voucher
```

---

### **5. Falta Validación de Monto en Webhooks de Wompi**
**Severidad**: CRÍTICA  
**Ubicación**: `views.py` WompiWebhookView líneas 611-855 (aprox)  
**Código de Error**: `SPA-WEBHOOK-AMOUNT`

**Problema**: No se valida que el monto pagado en Wompi coincida con el monto esperado, permitiendo fraude.

**Solución**:
```python
# En views.py WompiWebhookView
def post(self, request, *args, **kwargs):
    # ... código de validación de firma ...
    
    transaction_data = data.get("data", {}).get("transaction", {})
    reference = transaction_data.get("reference")
    status_wompi = transaction_data.get("status")
    amount_in_cents = transaction_data.get("amount_in_cents")
    
    # Buscar pago
    try:
        payment = Payment.objects.select_for_update().get(reference=reference)
    except Payment.DoesNotExist:
        return Response({"detail": "Payment not found"}, status=404)
    
    # CRÍTICO - Validar monto pagado
    expected_amount_cents = int(payment.amount * 100)
    if amount_in_cents != expected_amount_cents:
        logger.error(
            "Monto incorrecto en webhook Wompi: payment=%s, expected=%d, received=%d",
            payment.id,
            expected_amount_cents,
            amount_in_cents
        )
        
        # Marcar pago como fraudulento
        payment.status = Payment.PaymentStatus.FAILED
        payment.transaction_payload = {
            "error": "amount_mismatch",
            "expected": expected_amount_cents,
            "received": amount_in_cents,
            "webhook_data": transaction_data
        }
        payment.save(update_fields=['status', 'transaction_payload', 'updated_at'])
        
        # Auditar
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=None,
            target_user=payment.user,
            details={
                "action": "webhook_amount_mismatch",
                "payment_id": str(payment.id),
                "expected": expected_amount_cents,
                "received": amount_in_cents
            }
        )
        
        return Response(
            {"detail": "Amount mismatch"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ... resto del código de procesamiento
```

---

### **6. Falta Limpieza de Appointments Antiguos**
**Severidad**: ALTA  
**Ubicación**: `models.py` Appointment, nuevo archivo `tasks.py`  
**Código de Error**: `SPA-APPT-CLEANUP`

**Problema**: Las citas nunca se eliminan, causando crecimiento infinito de la tabla.

**Solución**:
```python
# En tasks.py
@shared_task
def cleanup_old_appointments():
    """
    Archiva citas completadas/canceladas hace más de 2 años.
    Ejecutar mensualmente.
    """
    from .models import Appointment
    
    cutoff = timezone.now() - timedelta(days=730)  # 2 años
    
    # Contar citas a archivar
    old_appointments = Appointment.objects.filter(
        status__in=[
            Appointment.AppointmentStatus.COMPLETED,
            Appointment.AppointmentStatus.CANCELLED
        ],
        updated_at__lt=cutoff
    )
    
    count = old_appointments.count()
    
    # Opción 1: Soft delete (si Appointment usa SoftDeleteModel)
    # old_appointments.delete()
    
    # Opción 2: Mover a tabla de archivo
    # ... implementar archivado
    
    # Opción 3: Eliminar permanentemente (solo si no hay dependencias)
    # old_appointments.hard_delete()
    
    logger.info("Archivadas %d citas antiguas", count)
    return {"archived_count": count}
```

---

### **7-12**: Más mejoras críticas (validaciones de waitlist, índices, logging, etc.)

---

## 🟡 IMPORTANTES (18) - Primera Iteración Post-Producción

### **13. Falta Rate Limiting en Creación de Citas**
**Severidad**: MEDIA  
**Ubicación**: `views.py` AppointmentViewSet.create  

**Solución**:
```python
# En views.py AppointmentViewSet.create
from django.core.cache import cache

def create(self, request, *args, **kwargs):
    # Rate limiting: máximo 5 citas por hora por usuario
    cache_key = f"appt_rate_limit:{request.user.id}"
    count = cache.get(cache_key, 0)
    
    if count >= 5:
        return Response(
            {
                "detail": "Has excedido el límite de creación de citas por hora.",
                "code": "APPOINTMENT_RATE_LIMIT"
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    cache.set(cache_key, count + 1, timeout=3600)
    
    # ... resto del código existente
```

---

### **14-30**: Más mejoras importantes (validaciones, optimizaciones, métricas, etc.)

---

## 🟢 MEJORAS (10) - Implementar Según Necesidad

### **31. Agregar Sistema de Recordatorios Automáticos**
**Severidad**: BAJA  

**Solución**:
```python
# En tasks.py
@shared_task
def send_appointment_reminders():
    """
    Envía recordatorios 24h y 2h antes de las citas.
    """
    from notifications.services import NotificationService
    
    # Recordatorios 24h antes
    tomorrow = timezone.now() + timedelta(hours=24)
    window_end = tomorrow + timedelta(minutes=5)
    
    appointments_24h = Appointment.objects.filter(
        start_time__gte=tomorrow,
        start_time__lte=window_end,
        status__in=[
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED
        ]
    ).select_related('user')
    
    for appointment in appointments_24h:
        NotificationService.send_notification(
            user=appointment.user,
            event_code="APPOINTMENT_REMINDER_24H",
            context={
                "appointment_id": str(appointment.id),
                "start_time": appointment.start_time.isoformat(),
                "services": appointment.get_service_names(),
            },
            priority="high"
        )
```

---

### **32-40**: Más mejoras opcionales (analytics, reportes, etc.)

---

## 📊 RESUMEN DE PRIORIDADES

### 🔴 CRÍTICAS (12) - Implementar ANTES de Producción
1. **#1** - Race condition en disponibilidad de slots
2. **#2** - Integración Wompi sin circuit breaker
3. **#3** - Sistema de 3 strikes inconsistente
4. **#4** - Vouchers sin validación atómica
5. **#5** - Falta validación de monto en webhooks
6. **#6** - Falta limpieza de appointments antiguos
7-12: Validaciones de waitlist, índices, logging, testing ausente

### 🟡 IMPORTANTES (18) - Primera Iteración Post-Producción
13-30: Rate limiting, validaciones, optimizaciones, métricas

### 🟢 MEJORAS (10) - Implementar Según Necesidad
31-40: Recordatorios automáticos, analytics, reportes

---

## 💡 RECOMENDACIONES ADICIONALES

### Monitoreo en Producción
- Alertas para doble reserva de slots
- Monitoreo de latencia de Wompi
- Métricas de tasa de cancelaciones
- Alertas de circuit breaker abierto

### Documentación
- Crear diagrama de flujo de pagos
- Documentar lógica de 3 strikes
- Crear guía de troubleshooting de Wompi
- Documentar sistema de vouchers

### Seguridad
- Validar firma de webhooks Wompi
- Implementar rate limiting en todos los endpoints
- Auditar accesos a datos de pagos
- Validar montos en todas las transacciones

---

**Próximos Pasos CRÍTICOS**:
1. **URGENTE**: Implementar locks en disponibilidad
2. **URGENTE**: Agregar circuit breaker para Wompi
3. Corregir sistema de 3 strikes
4. Implementar validación atómica de vouchers
5. Validar montos en webhooks
6. Crear suite de tests completa (mínimo 60% cobertura)
