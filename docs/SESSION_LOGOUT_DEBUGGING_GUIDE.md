# Guía de Debugging: Problema de Cierre de Sesión Inesperado

## Problema

Los clientes están experimentando cierres de sesión inesperados cuando:
- Un admin les crea una cita
- Un admin les registra un pago
- Un admin les actualiza datos
- Ellos mismos realizan acciones (agendar, pagar, cancelar)

## Sistema de Logging Implementado

Se han agregado logs exhaustivos para rastrear exactamente qué está causando los cierres de sesión. Todos los logs usan prefijos específicos para facilitar el filtrado.

### Logs de Sesiones

#### 1. Refresh de Tokens (`[SESSION_REFRESH]`)

**Ubicación**: `users/serializers.py:SessionAwareTokenRefreshSerializer`

**Logs generados**:
```
[SESSION_REFRESH] Intentando refrescar token - JTI: abc123..., user_id: +573001234567
[SESSION_REFRESH] Sesión encontrada - ID: uuid-..., User: +573001234567, IP: 192.168.1.1
[SESSION_REFRESH] Token rotado - User: +573001234567, Old JTI: abc123..., New JTI: xyz789...
```

**Logs de error**:
```
[SESSION_REFRESH_FAILED] Sesión NO encontrada - JTI: abc123..., user_id: +573001234567
[SESSION_DEBUG] Usuario +573001234567 tiene 2 sesiones activas con JTIs: ['xyz789...', 'def456...']
```

#### 2. Creación de Sesiones (`[SESSION_CREATED]`)

**Ubicación**: `users/signals.py:log_user_session_changes`

```
[SESSION_CREATED] Nueva sesión para +573001234567 - ID: uuid-..., JTI: abc123..., IP: 192.168.1.1
```

#### 3. Desactivación de Sesiones (`[SESSION_DEACTIVATED]`)

**Ubicación**: `users/signals.py:log_user_session_changes`

```
[SESSION_DEACTIVATED] Sesión uuid-... marcada como inactiva para +573001234567. JTI: abc123.... Llamado desde:
  File "/app/users/views/utils.py", line 95, in revoke_all_sessions
    ).update(is_active=False, updated_at=timezone.now())
  File "/app/users/views/password.py", line 130, in post
    revoke_all_sessions(user)
```

**IMPORTANTE**: Este log incluye el **stack trace completo** para ver exactamente qué código llamó la desactivación.

#### 4. Revocación de Todas las Sesiones (`[REVOKE_ALL_SESSIONS]`)

**Ubicación**: `users/views/utils.py:revoke_all_sessions`

```
[REVOKE_ALL_SESSIONS] Revocando todas las sesiones para +573001234567. Llamado desde:
  File "/app/users/views/password.py", line 130, in post
    revoke_all_sessions(user)
  ...

[REVOKE_ALL_SESSIONS] Usuario +573001234567: 3 tokens blacklisted, 2 sesiones invalidadas.
Sesiones afectadas: [
  {'id': 'uuid-1', 'refresh_token_jti': 'abc123', 'ip_address': '192.168.1.1', 'created_at': '2026-01-03T10:00:00Z'},
  {'id': 'uuid-2', 'refresh_token_jti': 'xyz789', 'ip_address': '192.168.1.2', 'created_at': '2026-01-03T11:00:00Z'}
]
```

#### 5. Modificaciones de Usuario (`[USER_SAVE]`)

**Ubicación**: `users/signals.py:audit_role_change`

```
[USER_SAVE] Usuario +573001234567 modificado. Campos cambiados: role: CLIENT -> VIP. Llamado desde:
  File "/app/spa/views/packages.py", line 57, in post
    user.save(update_fields=['vip_auto_renew', 'updated_at'])
  ...
```

#### 6. Creación de Citas por Admin (`[ADMIN_CREATE_APPOINTMENT]`)

**Ubicación**: `spa/views/appointments/appointment_viewset.py:admin_create_for_client`

```
[ADMIN_CREATE_APPOINTMENT] Admin +573009876543 creando cita para cliente +573001234567. Método de pago: PAYMENT_LINK
[ADMIN_CREATE_APPOINTMENT] Cita uuid-... creada exitosamente para cliente +573001234567
```

## Cómo Usar los Logs

### En Desarrollo (Local)

Los logs se imprimen en la consola donde corre Django:

```bash
# Filtrar solo logs de sesiones
./venv/Scripts/python.exe manage.py runserver 2>&1 | Select-String "SESSION"

# Filtrar solo logs de REVOKE
./venv/Scripts/python.exe manage.py runserver 2>&1 | Select-String "REVOKE"

# Ver todo el flujo cuando se crea una cita
./venv/Scripts/python.exe manage.py runserver 2>&1 | Select-String "ADMIN_CREATE_APPOINTMENT|SESSION"
```

### En Producción

Los logs están configurados en `studiozens/settings/logging.py`. Para ver logs de sesiones:

```bash
# Si usas Render/Railway/Heroku
heroku logs --tail | grep SESSION

# Si usas Docker
docker logs -f <container_name> | grep SESSION

# Si tienes Sentry configurado
# Los logs aparecerán en Sentry con los tags correspondientes
```

## Escenarios a Monitorear

### Escenario 1: Admin crea cita para un cliente

**Qué buscar en los logs**:

1. Log de creación de cita:
   ```
   [ADMIN_CREATE_APPOINTMENT] Admin +57300... creando cita para cliente +57301...
   ```

2. ¿Se llama `revoke_all_sessions`?
   ```
   [REVOKE_ALL_SESSIONS] Revocando todas las sesiones para +57301...
   ```

   **Si aparece**: El problema está en el backend - hay código que invalida sesiones inesperadamente.

   **Si NO aparece**: El problema está en el frontend o en la rotación de tokens.

3. ¿El cliente intenta refrescar su token después?
   ```
   [SESSION_REFRESH] Intentando refrescar token - JTI: abc123, user_id: +57301...
   [SESSION_REFRESH_FAILED] Sesión NO encontrada - JTI: abc123
   ```

   **Si aparece**: El problema es que el JTI del cliente ya no existe en la BD.

### Escenario 2: Cliente hace una acción y pierde sesión

**Qué buscar**:

1. ¿Hay modificaciones al usuario?
   ```
   [USER_SAVE] Usuario +57301... modificado. Campos cambiados: cancellation_streak
   ```

2. ¿Se desactiva la sesión?
   ```
   [SESSION_DEACTIVATED] Sesión ... marcada como inactiva para +57301...
   ```

3. El stack trace te dirá exactamente qué línea de código desactivó la sesión.

### Escenario 3: Problema de rotación de tokens (múltiples pestañas)

**Qué buscar**:

```
[SESSION_REFRESH] Token rotado - User: +57301..., Old JTI: abc123, New JTI: xyz789
[SESSION_REFRESH_FAILED] Sesión NO encontrada - JTI: abc123, user_id: +57301...
[SESSION_DEBUG] Usuario +57301... tiene 1 sesiones activas con JTIs: ['xyz789']
```

**Explicación**: Una pestaña/ventana refrescó el token primero (abc123 → xyz789), y cuando la segunda pestaña intentó refrescar con el JTI viejo (abc123), falló porque ya no existe.

## Próximos Pasos

1. **Reproducir el problema** con los logs activos
2. **Capturar los logs** exactos del momento en que ocurre el cierre de sesión
3. **Analizar el stack trace** en `[REVOKE_ALL_SESSIONS]` o `[SESSION_DEACTIVATED]` para ver qué código lo causó
4. **Compartir los logs** con el equipo de desarrollo para identificar el bug exacto

## Configuración de Logging

Si necesitas ajustar el nivel de logging:

```python
# En studiozens/settings/logging.py o settings.py
LOGGING = {
    'loggers': {
        'users': {
            'level': 'INFO',  # Cambiar a 'DEBUG' para más detalle
        },
        'spa': {
            'level': 'INFO',
        },
    }
}
```

## Notas Importantes

- Los logs con `logger.warning()` y `logger.error()` siempre se mostrarán
- Los logs con `logger.info()` solo se mostrarán si el nivel está en INFO o DEBUG
- El stack trace completo te dice EXACTAMENTE qué línea de código causó el problema
- Si ves `[SESSION_REFRESH_FAILED]` seguido de redirección a login, ahí está el problema

## Contacto

Si encuentras el problema en los logs, comparte:
1. El log completo de `[REVOKE_ALL_SESSIONS]` o `[SESSION_DEACTIVATED]`
2. El stack trace completo
3. El contexto (¿qué acción se estaba realizando?)
4. El timestamp para correlacionar con otros eventos
