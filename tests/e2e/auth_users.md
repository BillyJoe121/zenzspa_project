# 🧪 Pruebas E2E - Autenticación y Usuarios

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

## AUTH-001: Registro de Usuario Nuevo (Happy Path)
```
➡️ Navegar a /register
📱 Ingresar teléfono válido (+573157589548)
📱 Ingresar nombre "Juan"
📱 Ingresar apellido "Pérez"
📱 Ingresar email válido "juan@test.com"
📱 Ingresar contraseña válida "Test123!@#"
📱 Confirmar contraseña
➡️ Click en "Registrarse"
✅ Verificar redirección a /verify-otp
✅ Verificar que se muestra mensaje "Código enviado"
🔔 Verificar SMS recibido (mock Twilio)
📱 Ingresar código OTP válido
➡️ Click en "Verificar"
✅ Verificar redirección a /dashboard
✅ Verificar tokens JWT en localStorage
✅ Verificar usuario en estado is_verified=True
💾 Verificar ClinicalProfile creado automáticamente
💾 Verificar NotificationPreference creado
```

## AUTH-002: Registro con Teléfono Existente (Sad Path)
```
➡️ Navegar a /register
📱 Ingresar teléfono ya registrado
📱 Completar resto del formulario válido
➡️ Click en "Registrarse"
✅ Verificar error "Un usuario con este número de teléfono ya existe"
✅ Verificar que NO se envía SMS
✅ Verificar permanencia en /register
```

## AUTH-003: Registro con Teléfono Bloqueado/CNG (Sad Path)
```
➡️ Navegar a /register
📱 Ingresar teléfono en BlockedPhoneNumber
📱 Completar resto del formulario
➡️ Click en "Registrarse"
✅ Verificar error "Este número de teléfono está bloqueado"
💾 Verificar task send_non_grata_alert_to_admins ejecutada
🔔 Verificar notificación a admins
```

## AUTH-004: Registro con Contraseña Débil (Sad Path)
```
➡️ Navegar a /register
📱 Ingresar datos válidos
📱 Ingresar contraseña "123456"
➡️ Click en "Registrarse"
✅ Verificar error "Debe tener al menos 8 caracteres"
✅ Verificar error "Debe incluir al menos una letra mayúscula"
✅ Verificar error "Debe incluir al menos un símbolo"
```

## AUTH-005: Verificación OTP Expirado (Sad Path)
```
➡️ Completar registro exitoso
✅ Llegar a pantalla /verify-otp
⏱️ Esperar 10 minutos (o simular expiración)
📱 Ingresar código OTP
➡️ Click en "Verificar"
✅ Verificar error "El código de verificación es inválido o ha expirado"
✅ Verificar botón "Reenviar código" visible
```

## AUTH-006: Verificación OTP con Intentos Agotados (Sad Path)
```
➡️ Llegar a pantalla /verify-otp
📱 Ingresar código incorrecto
➡️ Click en "Verificar"
✅ Verificar error "Código inválido"
📱 Repetir 2 veces más (3 intentos totales)
✅ Verificar mensaje "Demasiados intentos. Inténtalo en X minutos"
✅ Verificar formulario deshabilitado
⏱️ Esperar período de lockout
✅ Verificar formulario habilitado nuevamente
```

## AUTH-007: Verificación OTP Requiere reCAPTCHA (Sad Path)
```
➡️ Generar múltiples intentos OTP desde misma IP
📱 Ingresar código en intento N+1
➡️ Click en "Verificar"
✅ Verificar que aparece reCAPTCHA
✅ Verificar error si no se completa reCAPTCHA
📱 Completar reCAPTCHA
📱 Ingresar código correcto
➡️ Click en "Verificar"
✅ Verificar login exitoso
```

## AUTH-008: Login con Credenciales Válidas (Happy Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono registrado y verificado
📱 Ingresar contraseña correcta
➡️ Click en "Iniciar Sesión"
✅ Verificar redirección a /dashboard
✅ Verificar access_token en localStorage
✅ Verificar refresh_token en localStorage
💾 Verificar UserSession creada
💾 Verificar last_login actualizado
```

## AUTH-009: Login con Usuario No Verificado (Sad Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono no verificado
📱 Ingresar contraseña correcta
➡️ Click en "Iniciar Sesión"
✅ Verificar error "El número de teléfono no ha sido verificado"
✅ Verificar botón "Reenviar verificación" visible
```

## AUTH-010: Login con Usuario CNG/Bloqueado (Sad Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono de usuario is_persona_non_grata=True
📱 Ingresar contraseña
➡️ Click en "Iniciar Sesión"
✅ Verificar error genérico (no revelar que está bloqueado)
✅ Verificar NO se genera token
```

## AUTH-011: Login con Múltiples Intentos Fallidos (Sad Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono válido
📱 Ingresar contraseña incorrecta 5 veces
✅ Verificar que aparece reCAPTCHA en intento 6
📱 No completar reCAPTCHA
➡️ Click en "Iniciar Sesión"
✅ Verificar error "Completa reCAPTCHA para continuar"
```

## AUTH-012: Refresh Token (Happy Path)
```
➡️ Login exitoso
✅ Obtener access_token y refresh_token
⏱️ Esperar expiración de access_token (15 min)
➡️ Hacer request a endpoint protegido
✅ Verificar que se hace refresh automático
✅ Verificar nuevo access_token
💾 Verificar UserSession.refresh_token_jti actualizado
```

## AUTH-013: Refresh Token Revocado (Sad Path)
```
➡️ Login exitoso en Dispositivo A
➡️ Login exitoso en Dispositivo B
➡️ En Dispositivo B: Cerrar todas las sesiones
➡️ En Dispositivo A: Intentar refresh
✅ Verificar error "Token inválido o revocado"
✅ Verificar redirección a /login
```

## AUTH-014: Logout Individual (Happy Path)
```
➡️ Login exitoso
➡️ Click en "Cerrar Sesión"
✅ Verificar tokens eliminados de localStorage
✅ Verificar redirección a /login
💾 Verificar refresh_token en BlacklistedToken
💾 Verificar UserSession.is_active=False
➡️ Intentar acceder a /dashboard
✅ Verificar redirección a /login
```

## AUTH-015: Logout de Todas las Sesiones (Happy Path)
```
➡️ Login en múltiples dispositivos (3 sesiones)
➡️ En dispositivo principal: Click "Cerrar todas las sesiones"
✅ Verificar logout en dispositivo actual
💾 Verificar todas las UserSession.is_active=False
💾 Verificar todos los tokens en BlacklistedToken
➡️ En otros dispositivos: Verificar sesión expirada
```

## AUTH-016: Recuperación de Contraseña (Happy Path)
```
➡️ Navegar a /forgot-password
📱 Ingresar teléfono registrado
➡️ Click en "Enviar Código"
✅ Verificar mensaje "Si existe una cuenta..."
🔔 Verificar SMS recibido
➡️ Navegar a /reset-password
📱 Ingresar código OTP
📱 Ingresar nueva contraseña válida
📱 Confirmar nueva contraseña
➡️ Click en "Restablecer"
✅ Verificar mensaje "Contraseña actualizada"
💾 Verificar todas las sesiones revocadas
➡️ Login con nueva contraseña
✅ Verificar login exitoso
```

## AUTH-017: Recuperación de Contraseña - Teléfono Inexistente (Sad Path)
```
➡️ Navegar a /forgot-password
📱 Ingresar teléfono no registrado
➡️ Click en "Enviar Código"
✅ Verificar mismo mensaje "Si existe una cuenta..." (no revelar)
✅ Verificar que NO se envía SMS
```

## AUTH-018: Cambio de Contraseña Autenticado (Happy Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/security
📱 Ingresar contraseña actual
📱 Ingresar nueva contraseña válida
📱 Confirmar nueva contraseña
➡️ Click en "Cambiar Contraseña"
✅ Verificar mensaje "Contraseña actualizada"
✅ Verificar logout automático
💾 Verificar todas las sesiones revocadas
➡️ Login con nueva contraseña
✅ Verificar login exitoso
```

## AUTH-019: Cambio de Contraseña - Contraseña Actual Incorrecta (Sad Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/security
📱 Ingresar contraseña actual incorrecta
📱 Ingresar nueva contraseña válida
➡️ Click en "Cambiar Contraseña"
✅ Verificar error "La contraseña actual es incorrecta"
✅ Verificar sesión NO cerrada
```

## AUTH-020: Gestión de Sesiones Activas (Happy Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/sessions
✅ Verificar lista de sesiones activas
✅ Verificar IP, User Agent, última actividad por sesión
➡️ Click en "Cerrar" en sesión específica
✅ Verificar sesión removida de lista
💾 Verificar UserSession.is_active=False
💾 Verificar token en BlacklistedToken
```

## AUTH-021: Configuración 2FA TOTP (Happy Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/security
➡️ Click en "Activar 2FA"
✅ Verificar código QR mostrado
✅ Verificar secret key mostrado
📱 Escanear QR con app autenticadora
📱 Ingresar código de 6 dígitos
➡️ Click en "Verificar"
✅ Verificar mensaje "2FA activado correctamente"
💾 Verificar user.totp_secret guardado
```

## AUTH-022: Login con 2FA Activo (Happy Path)
```
➡️ Navegar a /login (usuario con 2FA)
📱 Ingresar credenciales
➡️ Click en "Iniciar Sesión"
✅ Verificar redirección a /verify-2fa
📱 Ingresar código TOTP actual
➡️ Click en "Verificar"
✅ Verificar login exitoso
✅ Verificar redirección a /dashboard
```

## AUTH-023: Login con 2FA - Código Incorrecto (Sad Path)
```
➡️ Navegar a /login (usuario con 2FA)
📱 Ingresar credenciales
➡️ Click en "Iniciar Sesión"
📱 Ingresar código TOTP incorrecto
➡️ Click en "Verificar"
✅ Verificar error "Código inválido"
✅ Verificar permanencia en /verify-2fa
```
