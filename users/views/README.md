# Módulo Users Views - Refactorización en Progreso

## Estado Actual

El archivo monolítico original ya fue dividido. Mantenemos compatibilidad a través de `__init__.py`.

## Estructura Planificada

```
users/views/
├── __init__.py           # Exporta todas las vistas
├── README.md             # Este archivo
├── utils.py              # ✅ Funciones auxiliares (completado)
├── auth.py               # ✅ Reexporta las vistas de auth*
├── auth_registration.py  # ✅ Registro y reenvío OTP
├── auth_verification.py  # ✅ Verificación OTP
├── auth_tokens.py        # ✅ Emisión y refresh de tokens
├── auth_user.py          # ✅ Current user y self-delete
├── password.py           # Reset y cambio de contraseña
├── sessions.py           # Gestión de sesiones
├── totp.py               # 2FA/TOTP
├── admin_views.py        # ✅ Reexporta las vistas admin*
├── admin_flagging.py     # ✅ Flag CNG
├── admin_security.py     # ✅ Bloqueo de IP
├── admin_export.py       # ✅ Exportar usuarios
├── admin_staff.py        # ✅ Listado de staff
├── admin_user_viewset.py # ✅ CRUD admin de usuarios
└── webhooks.py           # Webhooks externos
```

## Archivos Completados

### ✅ utils.py
Funciones auxiliares compartidas:
- `log_otp_attempt()`: Registra intentos de OTP
- `requires_recaptcha()`: Verifica si se requiere reCAPTCHA
- `deactivate_session_for_jti()`: Desactiva sesión por JTI
- `revoke_all_sessions()`: Revoca todas las sesiones del usuario

### ✅ auth*
- `UserRegistrationView`, `ResendOTPView`, `VerifySMSView`, `CustomTokenObtainPairView`, `CustomTokenRefreshView`, `CurrentUserView`, `UserDeleteView`

### ✅ admin* (reexportadas en admin_views.py)
- `FlagNonGrataView`, `StaffListView`, `BlockIPView`, `UserExportView`, `AdminUserViewSet`

## Responsabilidades por Módulo

### auth.py (Completo)
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

### admin_views.py (Completo, reexporta admin_*.py)
- `FlagNonGrataView`: Marcar usuario como CNG
- `StaffListView`: Listar staff
- `BlockIPView`: Bloquear IP
- `UserExportView`: Exportar usuarios
- `AdminUserViewSet`: CRUD admin de usuarios

### webhooks.py (Pendiente)
- `TwilioWebhookView`: Webhook de Twilio
- `EmailVerificationView`: Verificación de email

## Próximos Pasos

1. Completar creación de archivos password.py, sessions.py, totp.py, webhooks.py
2. Validar imports en urls.py (ya debería apuntar a __init__.py)
3. Ejecutar tests de validación

## Notas Importantes

- Mantener compatibilidad total con imports existentes
- Todas las constantes de configuración ya están en utils.py
- Las funciones auxiliares usan imports relativos (`..models`, `..utils`)
