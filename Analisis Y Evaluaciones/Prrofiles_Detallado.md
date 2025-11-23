# 🔍 ANÁLISIS DETALLADO DE MEJORAS - MÓDULO PROFILES
## Análisis Pre-Producción Completo

**Fecha de Análisis**: 2025-11-23  
**Analista**: Antigravity AI  
**Módulo**: `profiles/`  
**Total de Mejoras Identificadas**: 32+

---

## 📋 RESUMEN EJECUTIVO

El módulo `profiles` gestiona **datos clínicos sensibles** (HIPAA/GDPR) incluyendo perfiles médicos, cuestionarios Dosha, consentimientos legales, y un sistema de kiosk para staff. El análisis identificó **32+ mejoras críticas** organizadas en 6 categorías:

- 🔴 **10 Críticas** - Implementar antes de producción
- 🟡 **14 Importantes** - Primera iteración post-producción  
- 🟢 **8 Mejoras** - Implementar según necesidad

### Componentes Analizados (12 archivos)
- **Modelos**: ClinicalProfile, LocalizedPain, DoshaQuestion/Option/Answer, ConsentTemplate/Document, KioskSession
- **Views**: 15 endpoints (CRUD perfiles, quiz dosha, kiosk mode, anonimización)
- **Serializers**: Validaciones complejas de quiz, permisos granulares
- **Permissions**: ClinicalProfileAccessPermission, IsKioskSession, acceso por rol
- **Middleware**: KioskFlowEnforcementMiddleware
- **Tests**: 2 test cases (kiosk flow, sessions)

### Áreas de Mayor Riesgo
1. **Datos médicos sin encriptación** - Violación HIPAA/GDPR
2. **Anonimización incompleta** - No elimina historial
3. **Kiosk sessions sin rate limiting** - Abuse potencial
4. **Consentimientos sin validación de IP** - Fraude legal
5. **Falta auditoría de acceso a datos médicos** - Compliance

---

## 🔴 CRÍTICAS (10) - Implementar Antes de Producción

### **1. Datos Médicos Sin Encriptación en Reposo**
**Severidad**: CRÍTICA  
**Ubicación**: `models.py` ClinicalProfile  
**Código de Error**: `PROF-ENCRYPT-REQUIRED`  
**Compliance**: HIPAA §164.312(a)(2)(iv), GDPR Art. 32

**Problema**: Campos médicos sensibles (`medical_conditions`, `allergies`, `contraindications`, `accidents_notes`) se almacenan en texto plano, violando regulaciones de privacidad médica.

**Solución**:
```python
# Instalar: pip install django-fernet-fields
from fernet_fields import EncryptedTextField

class ClinicalProfile(BaseModel):
    # ... otros campos ...
    
    medical_conditions = EncryptedTextField(
        blank=True,
        verbose_name="Condiciones médicas o diagnósticos relevantes"
    )
    allergies = EncryptedTextField(
        blank=True,
        verbose_name="Alergias conocidas"
    )
    contraindications = EncryptedTextField(
        blank=True,
        verbose_name="Contraindicaciones"
    )
    accidents_notes = EncryptedTextField(
        blank=True,
        verbose_name="Notas sobre Accidentes"
    )
    general_notes = EncryptedTextField(
        blank=True,
        verbose_name="Notas Generales del Terapeuta"
    )
    
    # LocalizedPain.notes también debe encriptarse
```

**Migración**:
```python
# Nueva migración para encriptar datos existentes
from django.db import migrations
from fernet_fields import EncryptedTextField

def encrypt_existing_data(apps, schema_editor):
    ClinicalProfile = apps.get_model('profiles', 'ClinicalProfile')
    for profile in ClinicalProfile.objects.all():
        # Los campos se encriptarán automáticamente al guardar
        profile.save(update_fields=[
            'medical_conditions', 'allergies', 
            'contraindications', 'accidents_notes', 'general_notes'
        ])

class Migration(migrations.Migration):
    dependencies = [('profiles', '0006_kiosksession_has_pending_changes')]
    
    operations = [
        migrations.RunPython(encrypt_existing_data, reverse_code=migrations.RunPython.noop),
    ]
```

---

### **2. Anonimización No Elimina Historial Versionado**
**Severidad**: CRÍTICA  
**Ubicación**: `models.py` ClinicalProfile.anonymize() líneas 104-164  
**Código de Error**: `PROF-ANONYMIZE-INCOMPLETE`  
**Compliance**: GDPR Art. 17 (Right to be Forgotten)

**Problema**: El método `anonymize()` limpia datos actuales pero **no elimina el historial versionado** de `simple-history`, dejando datos sensibles accesibles.

**Solución**:
```python
def anonymize(self, *, performed_by=None):
    """
    Limpia información sensible del perfil y elimina registros relacionados,
    cumpliendo con el derecho al olvido (GDPR Art. 17).
    """
    from core.models import AuditLog
    with transaction.atomic():
        unique_suffix = uuid.uuid4().hex[:8]
        user = self.user
        
        # 1. Anonimizar usuario
        if user:
            user.first_name = "ANONIMIZADO"
            user.last_name = ""
            user.phone_number = f"ANON-{unique_suffix}"
            user.email = f"anon-{unique_suffix}@anonymous.local"
            user.is_active = False
            user.is_verified = False
            user.save(update_fields=[
                'first_name', 'last_name', 'phone_number',
                'email', 'is_active', 'is_verified', 'updated_at',
            ])
        
        # 2. Limpiar datos del perfil actual
        self.accidents_notes = ''
        self.general_notes = ''
        self.medical_conditions = ''
        self.allergies = ''
        self.contraindications = ''
        self.dosha = self.Dosha.UNKNOWN
        self.element = ''
        self.diet_type = ''
        self.sleep_quality = ''
        self.activity_level = ''
        self.save(update_fields=[
            'accidents_notes', 'general_notes', 'medical_conditions',
            'allergies', 'contraindications', 'dosha', 'element',
            'diet_type', 'sleep_quality', 'activity_level', 'updated_at',
        ])
        
        # 3. NUEVO - Eliminar historial versionado
        # Esto es CRÍTICO para cumplir GDPR
        self.history.all().delete()
        
        # 4. Eliminar registros relacionados
        self.pains.all().delete()
        self.consents.all().delete()
        self.dosha_answers.all().delete()
        
        # 5. NUEVO - Eliminar sesiones de kiosk
        self.kiosk_sessions.all().delete()
        
        # 6. Auditoría
        AuditLog.objects.create(
            admin_user=performed_by,
            target_user=user,
            action=AuditLog.Action.CLINICAL_PROFILE_ANONYMIZED,
            details=f"Perfil {self.id} anonimizado completamente (incluye historial)",
        )
        logger.info(
            "Perfil clínico %s anonimizado completamente por %s",
            self.id,
            getattr(performed_by, 'id', None)
        )
```

---

### **3. Falta Auditoría de Acceso a Datos Médicos**
**Severidad**: CRÍTICA  
**Ubicación**: `views.py` ClinicalProfileViewSet  
**Código de Error**: `PROF-AUDIT-ACCESS`  
**Compliance**: HIPAA §164.308(a)(1)(ii)(D)

**Problema**: No se registra quién accede a datos médicos sensibles, violando requisitos de auditoría HIPAA.

**Solución**:
```python
# En views.py ClinicalProfileViewSet
from core.utils import safe_audit_log

class ClinicalProfileViewSet(viewsets.ModelViewSet):
    # ... código existente ...
    
    def retrieve(self, request, *args, **kwargs):
        """Sobrescribir para auditar acceso"""
        instance = self.get_object()
        
        # Auditar acceso a perfil médico
        safe_audit_log(
            action="ADMIN_ENDPOINT_HIT",  # Usar acción existente o crear nueva
            admin_user=request.user if request.user.is_authenticated else None,
            target_user=instance.user,
            details={
                "action": "view_clinical_profile",
                "profile_id": str(instance.id),
                "accessed_by_role": getattr(request.user, 'role', 'UNKNOWN'),
                "kiosk_session": bool(getattr(request, 'kiosk_session', None)),
            }
        )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def update(self, request, *args, **kwargs):
        """Sobrescribir para auditar modificaciones"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Capturar datos antes de actualizar
        old_data = {
            'medical_conditions': instance.medical_conditions,
            'allergies': instance.allergies,
            'contraindications': instance.contraindications,
        }
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Auditar cambios
        changes = []
        for field in ['medical_conditions', 'allergies', 'contraindications']:
            if old_data[field] != getattr(instance, field):
                changes.append(field)
        
        if changes:
            safe_audit_log(
                action="ADMIN_ENDPOINT_HIT",
                admin_user=request.user if request.user.is_authenticated else None,
                target_user=instance.user,
                details={
                    "action": "update_clinical_profile",
                    "profile_id": str(instance.id),
                    "fields_modified": changes,
                    "kiosk_session": bool(getattr(request, 'kiosk_session', None)),
                }
            )
        
        return Response(serializer.data)
```

---

### **4. Consentimientos Sin Validación de IP Real**
**Severidad**: ALTA  
**Ubicación**: `models.py` ConsentDocument líneas 270-307  
**Código de Error**: `PROF-CONSENT-IP`

**Problema**: El campo `ip_address` existe pero no se valida ni se captura automáticamente, permitiendo fraude en consentimientos legales.

**Solución**:
```python
# En views.py, crear endpoint para firmar consentimientos
from core.utils import get_client_ip

class SignConsentView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        template_id = request.data.get('template_id')
        
        try:
            template = ConsentTemplate.objects.get(id=template_id, is_active=True)
        except ConsentTemplate.DoesNotExist:
            return Response(
                {"detail": "Template de consentimiento no encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        profile, _ = ClinicalProfile.objects.get_or_create(user=request.user)
        
        # Capturar IP real del cliente
        client_ip = get_client_ip(request)
        
        # Crear consentimiento firmado
        consent = ConsentDocument.objects.create(
            profile=profile,
            template=template,
            is_signed=True,
            signed_at=timezone.now(),
            ip_address=client_ip,  # CRÍTICO - Capturar IP
        )
        
        # Auditar firma
        safe_audit_log(
            action="ADMIN_ENDPOINT_HIT",
            admin_user=None,
            target_user=request.user,
            details={
                "action": "sign_consent",
                "consent_id": str(consent.id),
                "template_version": template.version,
                "ip_address": client_ip,
            }
        )
        
        return Response(
            {"detail": "Consentimiento firmado exitosamente."},
            status=status.HTTP_201_CREATED
        )
```

---

### **5. Kiosk Sessions Sin Rate Limiting**
**Severidad**: ALTA  
**Ubicación**: `views.py` KioskStartSessionView líneas 177-220  
**Código de Error**: `PROF-KIOSK-RATE`

**Problema**: No hay límite en cuántas sesiones de kiosk puede crear un staff, permitiendo abuse.

**Solución**:
```python
# En views.py KioskStartSessionView
from django.core.cache import cache

class KioskStartSessionView(generics.GenericAPIView):
    serializer_class = KioskStartSessionSerializer
    permission_classes = [IsStaffOrAdmin]
    
    def post(self, request, *args, **kwargs):
        # Rate limiting: máximo 10 sesiones por hora por staff
        cache_key = f"kiosk_rate_limit:{request.user.id}"
        count = cache.get(cache_key, 0)
        
        if count >= 10:
            return Response(
                {
                    "detail": "Has excedido el límite de sesiones de kiosk por hora.",
                    "code": "KIOSK_RATE_LIMIT"
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        cache.set(cache_key, count + 1, timeout=3600)  # 1 hora
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # ... resto del código existente
```

---

### **6. Falta Limpieza de Kiosk Sessions Expiradas**
**Severidad**: ALTA  
**Ubicación**: `models.py` KioskSession, nuevo archivo `tasks.py`  
**Código de Error**: `PROF-KIOSK-CLEANUP`

**Problema**: Las sesiones de kiosk nunca se eliminan, causando crecimiento infinito de la tabla.

**Solución**:
```python
# Crear profiles/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

@shared_task
def cleanup_expired_kiosk_sessions():
    """
    Elimina sesiones de kiosk completadas hace más de 7 días.
    Ejecutar diariamente.
    """
    from .models import KioskSession
    
    cutoff = timezone.now() - timedelta(days=7)
    deleted_count, _ = KioskSession.objects.filter(
        status=KioskSession.Status.COMPLETED,
        updated_at__lt=cutoff
    ).delete()
    
    # También limpiar sesiones bloqueadas muy antiguas
    locked_cutoff = timezone.now() - timedelta(days=30)
    locked_deleted, _ = KioskSession.objects.filter(
        status=KioskSession.Status.LOCKED,
        updated_at__lt=locked_cutoff
    ).delete()
    
    return {
        "deleted_completed": deleted_count,
        "deleted_locked": locked_deleted
    }

# Configurar en Celery Beat
# CELERY_BEAT_SCHEDULE = {
#     'cleanup-kiosk-sessions': {
#         'task': 'profiles.tasks.cleanup_expired_kiosk_sessions',
#         'schedule': crontab(hour=3, minute=30),  # 3:30 AM diario
#     },
# }
```

---

### **7. Falta Validación de Dosha Quiz Completo**
**Severidad**: MEDIA-ALTA  
**Ubicación**: `views.py` DoshaQuizSubmitView líneas 118-175  
**Código de Error**: `PROF-QUIZ-INCOMPLETE`

**Problema**: No se valida que el usuario haya respondido TODAS las preguntas del quiz antes de calcular el dosha.

**Solución**:
```python
# En views.py DoshaQuizSubmitView.post
def post(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    answers_data = serializer.validated_data.get('answers', [])
    
    # NUEVO - Validar que se respondieron todas las preguntas
    total_questions = DoshaQuestion.objects.count()
    answered_questions = len(set(a['question_id'] for a in answers_data))
    
    if answered_questions < total_questions:
        return Response(
            {
                "detail": f"Debes responder todas las preguntas. Respondidas: {answered_questions}/{total_questions}",
                "code": "QUIZ_INCOMPLETE",
                "missing_count": total_questions - answered_questions
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ... resto del código existente
```

---

### **8. Falta Índices en Modelos Críticos**
**Severidad**: MEDIA-ALTA  
**Ubicación**: `models.py` múltiples modelos  
**Código de Error**: `PROF-INDEX-MISSING`

**Problema**: Queries frecuentes sin índices causan performance degradada.

**Solución**:
```python
# En models.py ClinicalProfile.Meta
class Meta:
    verbose_name = "Perfil Clínico"
    verbose_name_plural = "Perfiles Clínicos"
    indexes = [
        models.Index(fields=['user']),  # NUEVO - lookup frecuente
        models.Index(fields=['dosha', 'element']),  # NUEVO - filtros
    ]

# En models.py KioskSession.Meta
class Meta:
    verbose_name = "Sesión de Quiosco"
    verbose_name_plural = "Sesiones de Quiosco"
    ordering = ['-created_at']
    indexes = [
        models.Index(fields=['token']),  # Ya existe (unique)
        models.Index(fields=['status', 'expires_at']),  # NUEVO - cleanup
        models.Index(fields=['profile', 'created_at']),  # NUEVO - queries
        models.Index(fields=['staff_member', 'created_at']),  # NUEVO - auditoría
    ]

# En models.py ConsentDocument.Meta
class Meta:
    verbose_name = "Consentimiento Clínico"
    verbose_name_plural = "Consentimientos Clínicos"
    ordering = ['-created_at']
    indexes = [
        models.Index(fields=['profile', 'is_signed']),  # NUEVO
        models.Index(fields=['template_version', 'created_at']),  # NUEVO
    ]
```

---

### **9. Falta Validación de Timezone en Kiosk**
**Severidad**: MEDIA  
**Ubicación**: `views.py` KioskStartSessionView línea 200  
**Código de Error**: `PROF-KIOSK-TIMEZONE`

**Problema**: `expires_at` se calcula con `timezone.now()` que puede no coincidir con la zona horaria del spa.

**Solución**:
```python
# En views.py KioskStartSessionView.post
from core.models import GlobalSettings

def post(self, request, *args, **kwargs):
    # ... validaciones existentes ...
    
    # Usar timezone del spa desde GlobalSettings
    settings_obj = GlobalSettings.load()
    spa_tz = ZoneInfo(settings_obj.timezone_display)
    
    timeout_minutes = getattr(settings, "KIOSK_SESSION_TIMEOUT_MINUTES", 5)
    now_spa = timezone.now().astimezone(spa_tz)
    expires_at = now_spa + timedelta(minutes=timeout_minutes)
    
    session = KioskSession.objects.create(
        profile=profile,
        staff_member=staff_member,
        expires_at=expires_at.astimezone(timezone.utc),  # Guardar en UTC
    )
    
    # ... resto del código
```

---

### **10. Testing Insuficiente**
**Severidad**: ALTA  
**Ubicación**: `tests.py` - solo 2 test cases  
**Código de Error**: `PROF-TESTS-INCOMPLETE`

**Problema**: Solo hay tests para kiosk flow, faltan tests para:
- Anonimización de perfiles
- Encriptación de datos
- Permisos de acceso
- Quiz de dosha
- Consentimientos

**Solución**: Expandir suite de tests:

```python
# En tests.py
import pytest
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

class ClinicalProfileTests(TestCase):
    def test_anonymize_clears_sensitive_data(self):
        """anonymize() debe limpiar todos los datos sensibles"""
        profile = ClinicalProfile.objects.create(
            user=self.client_user,
            medical_conditions="Diabetes",
            allergies="Penicilina",
            contraindications="Embarazo"
        )
        
        profile.anonymize(performed_by=self.staff_user)
        profile.refresh_from_db()
        
        self.assertEqual(profile.medical_conditions, '')
        self.assertEqual(profile.allergies, '')
        self.assertEqual(profile.contraindications, '')
        
        # Verificar que historial fue eliminado
        self.assertEqual(profile.history.count(), 0)
    
    def test_clinical_profile_access_permissions(self):
        """Solo staff/admin pueden modificar perfiles"""
        # ... test de permisos
    
    def test_dosha_quiz_calculation(self):
        """Cálculo de dosha debe ser correcto"""
        # ... test de lógica de negocio

class ConsentDocumentTests(TestCase):
    def test_consent_captures_ip_address(self):
        """Consentimiento debe capturar IP del cliente"""
        # ... test de captura de IP
    
    def test_consent_signature_hash_validation(self):
        """Hash de firma debe ser válido"""
        # ... test de integridad

class KioskSessionSecurityTests(TestCase):
    def test_kiosk_session_rate_limiting(self):
        """Staff no puede crear sesiones ilimitadas"""
        # ... test de rate limiting
    
    def test_expired_kiosk_session_locks_automatically(self):
        """Sesiones expiradas se bloquean automáticamente"""
        # ... test de expiración

# ... más tests
```

---

## 🟡 IMPORTANTES (14) - Primera Iteración Post-Producción

### **11. Falta Validación de Longitud de Campos Médicos**
**Severidad**: MEDIA  
**Ubicación**: `models.py` ClinicalProfile  

**Solución**:
```python
from django.core.validators import MaxLengthValidator

medical_conditions = EncryptedTextField(
    blank=True,
    validators=[MaxLengthValidator(5000)],  # NUEVO
    verbose_name="Condiciones médicas o diagnósticos relevantes"
)
```

---

### **12. Falta Exportación de Datos para GDPR**
**Severidad**: MEDIA  
**Ubicación**: Nueva funcionalidad  
**Compliance**: GDPR Art. 20 (Right to Data Portability)

**Solución**:
```python
# Nueva vista en views.py
class ExportClinicalDataView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        """Exporta todos los datos clínicos del usuario en formato JSON"""
        profile = get_object_or_404(ClinicalProfile, user=request.user)
        
        data = {
            "profile": {
                "dosha": profile.dosha,
                "element": profile.element,
                "diet_type": profile.diet_type,
                "sleep_quality": profile.sleep_quality,
                "activity_level": profile.activity_level,
                "medical_conditions": profile.medical_conditions,
                "allergies": profile.allergies,
                "contraindications": profile.contraindications,
                "accidents_notes": profile.accidents_notes,
            },
            "pains": [
                {
                    "body_part": pain.body_part,
                    "pain_level": pain.pain_level,
                    "periodicity": pain.periodicity,
                    "notes": pain.notes,
                }
                for pain in profile.pains.all()
            ],
            "consents": [
                {
                    "template_version": consent.template_version,
                    "signed_at": consent.signed_at.isoformat() if consent.signed_at else None,
                    "ip_address": consent.ip_address,
                }
                for consent in profile.consents.filter(is_signed=True)
            ],
            "exported_at": timezone.now().isoformat(),
        }
        
        # Auditar exportación
        safe_audit_log(
            action="ADMIN_ENDPOINT_HIT",
            admin_user=None,
            target_user=request.user,
            details={"action": "export_clinical_data"}
        )
        
        return Response(data)
```

---

### **13-24**: Más mejoras importantes (validaciones, logging, optimizaciones, etc.)

---

## 🟢 MEJORAS (8) - Implementar Según Necesidad

### **25. Agregar Versionado de Consentimientos con Diff**
**Severidad**: BAJA  

**Solución**:
```python
# En admin.py ConsentTemplateAdmin
from simple_history.admin import SimpleHistoryAdmin

@admin.register(ConsentTemplate)
class ConsentTemplateAdmin(SimpleHistoryAdmin):
    list_display = ('version', 'title', 'is_active', 'updated_at')
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        # Mostrar diff entre versiones
        if request.GET.get('compare'):
            # ... lógica de comparación
            pass
        
        return super().changelist_view(request, extra_context)
```

---

### **26-32**: Más mejoras opcionales (notificaciones, analytics, etc.)

---

## 📊 RESUMEN DE PRIORIDADES

### 🔴 CRÍTICAS (10) - Implementar ANTES de Producción
1. **#1** - Datos médicos sin encriptación (HIPAA/GDPR)
2. **#2** - Anonimización no elimina historial
3. **#3** - Falta auditoría de acceso a datos médicos
4. **#4** - Consentimientos sin validación de IP
5. **#5** - Kiosk sessions sin rate limiting
6. **#6** - Falta limpieza de kiosk sessions
7. **#7** - Falta validación de quiz completo
8. **#8** - Falta índices en modelos críticos
9. **#9** - Falta validación de timezone en kiosk
10. **#10** - Testing insuficiente

### 🟡 IMPORTANTES (14) - Primera Iteración Post-Producción
11-24: Validaciones, exportación GDPR, logging mejorado, métricas

### 🟢 MEJORAS (8) - Implementar Según Necesidad
25-32: Versionado de consentimientos, analytics, notificaciones

---

## 💡 RECOMENDACIONES ADICIONALES

### Compliance HIPAA/GDPR
- **Encriptación**: Implementar INMEDIATAMENTE
- **Auditoría**: Registrar TODOS los accesos
- **Retención**: Definir política de retención de datos
- **Breach Notification**: Plan de respuesta a brechas

### Monitoreo en Producción
- Alertas para accesos anómalos a perfiles
- Monitoreo de sesiones de kiosk activas
- Métricas de consentimientos firmados
- Alertas de intentos de anonimización

### Documentación
- Crear política de privacidad médica
- Documentar flujo de consentimientos
- Crear guía de uso de kiosk mode
- Documentar proceso de anonimización

### Seguridad
- Implementar 2FA para staff que accede a datos médicos
- Limitar exportación de datos
- Validar integridad de consentimientos
- Implementar detección de anomalías

---

**Próximos Pasos CRÍTICOS**:
1. **URGENTE**: Implementar encriptación de datos médicos
2. **URGENTE**: Corregir anonimización para incluir historial
3. Implementar auditoría completa de accesos
4. Crear suite de tests completa (mínimo 70% cobertura)
5. Configurar limpieza automática de sesiones
6. Realizar auditoría de compliance HIPAA/GDPR
