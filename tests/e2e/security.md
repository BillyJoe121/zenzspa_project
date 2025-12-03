# 🧪 Pruebas E2E - Seguridad

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

## SEC-001: SQL Injection en Búsqueda
```
➡️ Navegar a /shop?search=' OR '1'='1
✅ Verificar error 400 o resultados vacíos
✅ Verificar NO se expone error de BD
```

## SEC-002: XSS en Campos de Texto
```
📱 Ingresar <script>alert('XSS')</script> en notas
➡️ Guardar y ver
✅ Verificar script escapado/no ejecutado
```

## SEC-003: CSRF Token Requerido
```
➡️ Hacer POST sin CSRF token
✅ Verificar error 403 Forbidden
```

## SEC-004: JWT Expirado
```
⏱️ Esperar expiración de access_token
➡️ Hacer request con token expirado
✅ Verificar error 401 Unauthorized
```

## SEC-005: Acceso a Recurso de Otro Usuario
```
➡️ Login como USER-A
➡️ Intentar ver cita de USER-B
✅ Verificar error 403 o 404
```

## SEC-006: Escalación de Privilegios
```
➡️ Login como CLIENT
➡️ Intentar acceder a /admin/users
✅ Verificar error 403 Forbidden
```

## SEC-007: Rate Limiting Global
```
➡️ Enviar 101 requests en 1 minuto (límite=100)
✅ Verificar error 429 Too Many Requests
✅ Verificar header Retry-After
```

## SEC-008: Fuerza Bruta en Login
```
➡️ Intentar 10 logins fallidos seguidos
✅ Verificar cuenta bloqueada temporalmente
✅ Verificar reCAPTCHA requerido
```
