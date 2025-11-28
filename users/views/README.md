# Módulo Users Views - Refactorización en Progreso

## Estado Actual

El archivo `users/views.py` (~630 líneas) está siendo refactorizado en una estructura modular.

## Estructura Planificada

```
users/views/
├── __init__.py           # Exporta todas las vistas
├── README.md             # Este archivo
├── utils.py              # ✅ Funciones auxiliares (completado)
├── auth.py               # Autenticación y registro
├── password.py           # Reset y cambio de contraseña
├── sessions.py           # Gestión de sesiones
├── totp.py               # 2FA/TOTP
├── admin_views.py        # Vistas administrativas
└── webhooks.py           # Webhooks externos
```

## Archivos Completados

### ✅ utils.py
Funciones auxiliares compartidas:
- `log_otp_attempt()`: Registra intentos de OTP
- `requires_recaptcha()`: Verifica si se requiere reCAPTCHA
- `deactivate_session_for_jti()`: Desactiva sesión por JTI
- `revoke_all_sessions()`: Revoca todas las sesiones del usuario

## Responsabilidades por Módulo

### auth.py (Pendiente)
- `UserRegistrationView`: Registro de usuarios
- `VerifySMSView`: Verificación de códigos SMS
- `CustomTokenObtainPairView`: Obtener tokens JWT
- `CustomTokenRefreshView`: Refrescar tokens
- `CurrentUserView`: Información del usuario actual

### password.py (Pendiente)
- `PasswordResetRequestView`: Solicitar reset de contraseña
- `PasswordResetConfirmView`: Confirmar reset con código
- `ChangePasswordView`: Cambiar contraseña (autenticado)

### sessions.py (Pendiente)
- `LogoutView`: Cerrar sesión individual
- `LogoutAllView`: Cerrar todas las sesiones
- `UserSessionListView`: Listar sesiones activas
- `UserSessionDeleteView`: Eliminar sesión específica

### totp.py (Pendiente)
- `TOTPSetupView`: Configurar 2FA
- `TOTPVerifyView`: Verificar código 2FA

### admin_views.py (Pendiente)
- `FlagNonGrataView`: Marcar usuario como CNG
- `StaffListView`: Listar staff
- `BlockIPView`: Bloquear IP
- `UserExportView`: Exportar usuarios

### webhooks.py (Pendiente)
- `TwilioWebhookView`: Webhook de Twilio
- `EmailVerificationView`: Verificación de email

## Próximos Pasos

1. Completar creación de archivos auth.py, password.py, sessions.py
2. Completar totp.py, admin_views.py, webhooks.py
3. Crear __init__.py con exportaciones
4. Actualizar imports en urls.py
5. Ejecutar tests de validación
6. Renombrar archivo original a views.py.old

## Notas Importantes

- Mantener compatibilidad total con imports existentes
- Todas las constantes de configuración ya están en utils.py
- Las funciones auxiliares usan imports relativos (`..models`, `..utils`)
